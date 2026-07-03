import os
import zipfile
import tempfile
import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path

from cli.hipforge import zip_project, download_and_extract, run_migration

@pytest.fixture
def temp_project():
    """Create a temporary directory structure to simulate a project."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        # Create a sample CUDA file
        cuda_file = tmp_path / "kernel.cu"
        cuda_file.write_text("int main() {}", encoding="utf-8")
        
        # Create a subdirectory with another file
        subdir = tmp_path / "src"
        subdir.mkdir()
        sub_file = subdir / "helper.h"
        sub_file.write_text("// helper", encoding="utf-8")
        
        # Create a hidden file that should be ignored
        hidden = tmp_path / ".hidden_config"
        hidden.write_text("hidden", encoding="utf-8")
        
        yield tmp_path

def test_zip_project(temp_project):
    zip_path = zip_project(temp_project)
    
    assert zip_path.exists()
    assert zipfile.is_zipfile(zip_path)
    
    # Check zip contents
    with zipfile.ZipFile(zip_path, 'r') as zipf:
        namelist = zipf.namelist()
        assert "kernel.cu" in namelist
        assert "src/helper.h" in namelist
        assert ".hidden_config" not in namelist  # Hidden files ignored
        
    if zip_path.exists():
        os.remove(zip_path)

@patch("cli.hipforge.requests.get")
def test_download_and_extract(mock_get, tmp_path):
    # Prepare dummy zip content
    dummy_zip = tmp_path / "dummy.zip"
    with zipfile.ZipFile(dummy_zip, 'w') as zipf:
        zipf.writestr("migrated.hip", "/* converted hip */")
        
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = dummy_zip.read_bytes()
    mock_get.return_code = 200
    mock_get.return_value = mock_resp
    
    output_dir = tmp_path / "extracted_project"
    success = download_and_extract("http://localhost:8000", "test_id", output_dir)
    
    assert success
    assert (output_dir / "migrated.hip").exists()
    assert (output_dir / "migrated.hip").read_text(encoding="utf-8") == "/* converted hip */"


@pytest.mark.asyncio
@patch("cli.hipforge.requests.post")
@patch("cli.hipforge.websockets.connect")
@patch("cli.hipforge.download_and_extract")
async def test_run_migration_success(mock_download_extract, mock_ws_connect, mock_post, temp_project, tmp_path):
    # Mock POST upload response
    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 202
    mock_post_resp.json.return_value = {"migration_id": "test_id", "status": "QUEUED"}
    mock_post.return_value = mock_post_resp
    
    # Mock WebSocket Connection
    mock_ws = AsyncMock()
    # Define messages to be sent over WS
    ws_messages = [
        '{"type": "status", "status": "QUEUED"}',
        '{"type": "log", "message": "Queue processed"}',
        '{"type": "status", "status": "COMPLETED"}'
    ]
    
    class MockWSContext:
        async def __aenter__(self):
            return mock_ws
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass
            
    mock_ws_connect.return_value = MockWSContext()
    
    # Define side effect for ws.recv() to stream the messages and then simulate close
    recv_queue = asyncio.Queue()
    for msg in ws_messages:
        recv_queue.put_nowait(msg)
        
    async def mock_recv():
        if not recv_queue.empty():
            return recv_queue.get_nowait()
        # Simulate connection closed
        from websockets.exceptions import ConnectionClosedOK
        raise ConnectionClosedOK(None, None)
        
    mock_ws.recv.side_effect = mock_recv
    
    # Mock download extraction success
    mock_download_extract.return_value = True
    
    output_dir = tmp_path / "output"
    await run_migration(temp_project, "gfx90a", output_dir, "http://localhost:8000")
    
    # Verify requests were called correctly
    mock_post.assert_called_once()
    mock_ws_connect.assert_called_once_with("ws://localhost:8000/ws/v1/migrate/test_id/stream")
    mock_download_extract.assert_called_once_with("http://localhost:8000", "test_id", output_dir)
