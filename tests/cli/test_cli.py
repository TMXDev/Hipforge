import os
import sys
import zipfile
import tempfile
import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path

from cli.hipforge import zip_project, download_and_extract, run_migration, run_doctor_command


# ── fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def temp_project():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        (tmp_path / "kernel.cu").write_text("int main() {}", encoding="utf-8")
        sub = tmp_path / "src"
        sub.mkdir()
        (sub / "helper.h").write_text("// helper", encoding="utf-8")
        (tmp_path / ".hidden_config").write_text("hidden", encoding="utf-8")
        yield tmp_path


# ── existing unit tests (kept) ─────────────────────────────────────────────

def test_zip_project(temp_project):
    zip_path = zip_project(temp_project)
    assert zip_path.exists()
    assert zipfile.is_zipfile(zip_path)
    with zipfile.ZipFile(zip_path, "r") as zipf:
        namelist = zipf.namelist()
        assert "kernel.cu" in namelist
        assert "src/helper.h" in namelist
        assert ".hidden_config" not in namelist
    if zip_path.exists():
        os.remove(zip_path)


@patch("cli.hipforge.requests.get")
def test_download_and_extract(mock_get, tmp_path):
    dummy_zip = tmp_path / "dummy.zip"
    with zipfile.ZipFile(dummy_zip, "w") as zipf:
        zipf.writestr("migrated.hip", "/* converted hip */")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = dummy_zip.read_bytes()
    mock_get.return_value = mock_resp

    output_dir = tmp_path / "extracted_project"
    success = download_and_extract("http://localhost:8000", "test_id", output_dir)
    assert success
    assert (output_dir / "test_id" / "migrated.hip").read_text(encoding="utf-8") == "/* converted hip */"


# ── Task 1: no-args prints help, does not start interactive shell ──────────

def test_no_args_prints_help_and_exits(capsys):
    """hipforge with no args must print help and exit 0, never enter the REPL."""
    from cli.hipforge import main
    with patch("sys.argv", ["hipforge"]):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "usage" in (captured.out + captured.err).lower()


def test_unknown_subcommand_prints_help_and_exits(capsys):
    from cli.hipforge import main
    with patch("sys.argv", ["hipforge", "notacommand"]):
        with pytest.raises(SystemExit):
            main()
    # Should not block / hang


def test_shell_subcommand_calls_interactive():
    """hipforge shell must invoke run_interactive_cli."""
    from cli import hipforge
    with patch("sys.argv", ["hipforge", "shell"]):
        with patch.object(hipforge, "run_interactive_cli") as mock_repl:
            hipforge.main()
            mock_repl.assert_called_once()


def test_interactive_subcommand_calls_interactive():
    from cli import hipforge
    with patch("sys.argv", ["hipforge", "interactive"]):
        with patch.object(hipforge, "run_interactive_cli") as mock_repl:
            hipforge.main()
            mock_repl.assert_called_once()


# ── Task 2 & 3: WS fallback polling ───────────────────────────────────────

@pytest.mark.asyncio
@patch("cli.hipforge.requests.post")
@patch("cli.hipforge.websockets.connect")
@patch("cli.hipforge.download_and_extract")
@patch("cli.hipforge.requests.get")
async def test_ws_disconnect_falls_back_to_polling(
    mock_get, mock_download_extract, mock_ws_connect, mock_post, temp_project, tmp_path
):
    """WS disconnect triggers polling fallback; polling finds COMPLETED."""
    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 202
    mock_post_resp.json.return_value = {"migration_id": "poll_id", "status": "QUEUED"}
    mock_post.return_value = mock_post_resp

    # WebSocket connect raises immediately -> stream_logs returns None
    mock_ws_connect.side_effect = Exception("connection refused")

    call_count = 0

    def get_side_effect(url, **kwargs):
        nonlocal call_count
        # journal endpoint -> return list so journal iteration works
        if "/journal" in url:
            return MagicMock(status_code=200, **{"json.return_value": []})
        call_count += 1
        if call_count <= 2:
            return MagicMock(status_code=200, **{"json.return_value": {"status": "RUNNING"}})
        return MagicMock(status_code=200, **{"json.return_value": {"status": "COMPLETED"}})

    mock_get.side_effect = get_side_effect
    mock_download_extract.return_value = True

    with patch.dict(os.environ, {"HIPFORGE_POLL_TIMEOUT": "30"}):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await run_migration(temp_project, "gfx90a", tmp_path / "out", "http://localhost:8000")

    assert call_count >= 2
    mock_download_extract.assert_called_once()


@pytest.mark.asyncio
@patch("cli.hipforge.requests.post")
@patch("cli.hipforge.websockets.connect")
@patch("cli.hipforge.download_and_extract")
@patch("cli.hipforge.requests.get")
async def test_polling_does_not_stop_after_5_attempts(
    mock_get, mock_download_extract, mock_ws_connect, mock_post, temp_project, tmp_path
):
    """Polling must continue past 5 attempts (old ceiling) until timeout or terminal state."""
    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 202
    mock_post_resp.json.return_value = {"migration_id": "long_id", "status": "QUEUED"}
    mock_post.return_value = mock_post_resp
    mock_ws_connect.side_effect = Exception("refused")
    mock_download_extract.return_value = True

    call_count = 0

    def get_side_effect(url, **kwargs):
        nonlocal call_count
        if "/journal" in url:
            return MagicMock(status_code=200, **{"json.return_value": []})
        call_count += 1
        status = "COMPLETED" if call_count > 8 else "RUNNING"
        return MagicMock(status_code=200, **{"json.return_value": {"status": status}})

    mock_get.side_effect = get_side_effect

    with patch.dict(os.environ, {"HIPFORGE_POLL_TIMEOUT": "120"}):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await run_migration(temp_project, "gfx90a", tmp_path / "out2", "http://localhost:8000")

    # Must have polled more than 5 times (old ceiling was 5)
    assert call_count > 5


# ── Task 4: doctor remote-first ───────────────────────────────────────────

@patch("cli.hipforge.requests.get")
def test_doctor_default_calls_remote(mock_get):
    """Default doctor (local=False) must query the backend, not run local preflight."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"health_score": 100, "overall_status": "ok", "critical_failures": []}
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    with patch("cli.hipforge._load_backend_diagnostics") as mock_diag:
        run_doctor_command("http://localhost:8000", local=False)
        mock_diag.assert_not_called()
    mock_get.assert_called_once()


@patch("cli.hipforge.requests.get")
def test_doctor_local_flag_runs_preflight(mock_get):
    """--local must call run_preflight instead of HTTP."""
    fake_report = {"health_score": 80, "overall_status": "warn", "critical_failures": []}
    mock_preflight = MagicMock(return_value=fake_report)

    with patch("cli.hipforge._load_backend_diagnostics", return_value=(mock_preflight, None)):
        run_doctor_command("http://localhost:8000", local=True)
        mock_preflight.assert_called_once()
    # HTTP must NOT have been called (preflight returned data)
    mock_get.assert_not_called()


# ── Task 5: failed terminal state prints failed summary ───────────────────

@pytest.mark.asyncio
@patch("cli.hipforge.requests.post")
@patch("cli.hipforge.websockets.connect")
@patch("cli.hipforge.requests.get")
async def test_failed_terminal_state_no_download(
    mock_get, mock_ws_connect, mock_post, temp_project, tmp_path, capsys
):
    """FAILED final state must not attempt download and must print the migration ID."""
    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 202
    mock_post_resp.json.return_value = {"migration_id": "fail_id", "status": "QUEUED"}
    mock_post.return_value = mock_post_resp
    mock_ws_connect.side_effect = Exception("refused")

    def get_side_effect(url, **kwargs):
        if "/journal" in url:
            return MagicMock(status_code=200, **{"json.return_value": []})
        return MagicMock(
            status_code=200,
            **{"json.return_value": {"status": "FAILED", "main_error": "compilation error"}},
        )

    mock_get.side_effect = get_side_effect

    with patch.dict(os.environ, {"HIPFORGE_POLL_TIMEOUT": "10"}):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            with patch("cli.hipforge.download_and_extract") as mock_dl:
                await run_migration(temp_project, "gfx90a", tmp_path / "out3", "http://localhost:8000")
                mock_dl.assert_not_called()

    out = capsys.readouterr().out
    assert "fail_id" in out
