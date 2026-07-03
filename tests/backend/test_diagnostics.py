from pathlib import Path

import pytest

from app.config.settings import settings
from app.diagnostics import (
    ERROR_CONFIGURATION,
    ERROR_ENVIRONMENT,
    run_preflight,
    run_self_test,
)


def _check(report, check_id):
    return next(check for check in report["checks"] if check["id"] == check_id)


def test_preflight_missing_docker_fails_gracefully(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "USE_MOCK_COMPILER", False)
    monkeypatch.setattr(settings, "USE_MOCK_AI", True)
    monkeypatch.setattr("app.diagnostics._docker_client", lambda: (None, RuntimeError("Docker daemon unavailable")))

    report = run_preflight(workspace_path=str(tmp_path), run_container_checks=False)

    docker_check = _check(report, "docker_sdk")
    assert docker_check["status"] == "fail"
    assert docker_check["critical"] is True
    assert "Docker daemon unavailable" in docker_check["message"]
    assert report["critical_failures"]
    assert report["readiness"] == "NOT_READY"


def test_preflight_missing_fireworks_key_is_configuration_error(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "USE_MOCK_COMPILER", True)
    monkeypatch.setattr(settings, "USE_MOCK_AI", False)
    monkeypatch.setattr(settings, "FIREWORKS_API_KEY", "your_fireworks_api_key")

    report = run_preflight(workspace_path=str(tmp_path), run_container_checks=False)

    key_check = _check(report, "fireworks_api_key")
    assert key_check["status"] == "fail"
    assert key_check["category"] == ERROR_CONFIGURATION
    assert key_check["critical"] is True
    assert "FIREWORKS_API_KEY" in key_check["message"]


def test_preflight_invalid_fireworks_model_is_ai_error(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "USE_MOCK_COMPILER", True)
    monkeypatch.setattr(settings, "USE_MOCK_AI", False)
    monkeypatch.setattr(settings, "FIREWORKS_API_KEY", "fw-test-key")

    def fake_fireworks_request(url, api_key, method="GET", payload=None, timeout=10):
        if method == "POST":
            return {"choices": []}
        return {"data": [{"id": "some-model"}]}

    monkeypatch.setattr("app.diagnostics._fireworks_request", fake_fireworks_request)

    report = run_preflight(workspace_path=str(tmp_path), run_container_checks=False)

    model_check = _check(report, "fireworks_model")
    assert model_check["status"] == "fail"
    assert model_check["category"] == "AI_ERROR"
    assert model_check["critical"] is True


class _FakeImages:
    def get(self, image_name):
        class _Image:
            tags = [image_name]
        return _Image()


class _FakeDocker:
    images = _FakeImages()

    def ping(self):
        return True

    def info(self):
        return {"ServerVersion": "test", "Runtimes": {}}


def test_preflight_missing_runsc_reports_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "USE_MOCK_COMPILER", True)
    monkeypatch.setattr(settings, "USE_MOCK_AI", True)
    monkeypatch.setattr(settings, "ALLOW_RUNSC_FALLBACK", True)
    monkeypatch.setattr("app.diagnostics._docker_client", lambda: (_FakeDocker(), None))

    report = run_preflight(workspace_path=str(tmp_path), run_container_checks=False)

    runsc_check = _check(report, "runsc")
    assert runsc_check["status"] == "warn"
    assert runsc_check["details"]["fallback_allowed"] is True
    assert "fallback is allowed" in runsc_check["message"]


def test_preflight_workspace_permission_error_is_deterministic(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "USE_MOCK_COMPILER", True)
    monkeypatch.setattr(settings, "USE_MOCK_AI", True)

    def fake_writable(path: Path):
        if path.name == "generated":
            return False, "permission denied"
        return True, ""

    monkeypatch.setattr("app.diagnostics._writable_path", fake_writable)

    report = run_preflight(workspace_path=str(tmp_path), run_container_checks=False)

    workspace_check = _check(report, "workspace_directories")
    assert workspace_check["status"] == "fail"
    assert workspace_check["critical"] is True
    assert workspace_check["category"] == ERROR_ENVIRONMENT
    assert "generated: permission denied" in workspace_check["details"]["problems"]


def test_preflight_corrupted_compiler_cache_fails_gracefully(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "USE_MOCK_COMPILER", True)
    monkeypatch.setattr(settings, "USE_MOCK_AI", True)
    cache_dir = tmp_path / ".cache"
    cache_dir.mkdir()
    (cache_dir / "bad.json").write_text("{not-json", encoding="utf-8")
    monkeypatch.setattr("app.diagnostics._compiler_cache_dir", lambda: cache_dir)

    report = run_preflight(workspace_path=str(tmp_path), run_container_checks=False)

    cache_check = _check(report, "compiler_cache")
    assert cache_check["status"] == "fail"
    assert cache_check["critical"] is True
    assert "bad.json" in cache_check["details"]["corrupt_files"][0]


def test_self_test_succeeds_in_mock_mode(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "USE_MOCK_COMPILER", True)
    monkeypatch.setattr(settings, "USE_MOCK_AI", True)
    monkeypatch.setattr(settings, "WORKSPACE_PATH", str(tmp_path))
    monkeypatch.setenv("USE_MOCK_COMPILER", "true")
    monkeypatch.setenv("USE_MOCK_AI", "true")

    report = run_self_test(cleanup=True)

    assert report["success"] is True
    assert [step["name"] for step in report["steps"]] == [
        "generate_project",
        "hipify",
        "compile",
        "verify_output",
    ]
