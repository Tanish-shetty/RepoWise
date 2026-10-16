from pathlib import Path

from app.services.analysis import analyze_repository
from app.services.indexer import CodeIndex, chunk_file
from app.services.repository import profile_repository
from fastapi.testclient import TestClient
from app.main import app
from app.api import _sanitize_workspace_paths
from app.services import agents
from app.services.agents import DebuggingWorkflow
from app.execution.sandbox import summarize_test_output


SAMPLE = Path(__file__).parents[2] / "examples" / "sample-python-project"


def test_profile_detects_python_project():
    profile, files = profile_repository(SAMPLE)
    assert profile["languages"][0]["name"] == "Python"
    assert profile["test_files"] >= 1
    assert files


def test_python_chunking_preserves_symbol_and_lines():
    chunks = chunk_file(1, "auth.py", "Python", "def login(name):\n    return name\n")
    assert chunks[0].symbol == "login"
    assert chunks[0].start_line == 1


def test_retrieval_finds_login_symbol():
    index = CodeIndex()
    index.index(7, SAMPLE)
    results = index.search(7, "failing login password")
    assert "authenticate_user" in {result["symbol"] for result in results[:3]}


def test_analysis_finds_generic_auth_exception():
    issues = analyze_repository(SAMPLE)
    assert any(issue.title == "Generic exception raised" and issue.file.endswith("auth.py") for issue in issues)


def test_api_import_scan_analyze_and_debug():
    with TestClient(app) as client:
        created = client.post("/api/repositories", json={"local_path": str(SAMPLE)})
        assert created.status_code == 201
        repository_id = created.json()["id"]
        scanned = client.post(f"/api/repositories/{repository_id}/scan")
        assert scanned.status_code == 200
        assert scanned.json()["profile"]["indexed_chunks"] > 0
        analysis = client.post("/api/analysis", json={"repository_id": repository_id})
        assert analysis.status_code == 201
        assert analysis.json()["result"]["issues"]
        finding = analysis.json()["result"]["issues"][0]
        assert finding["why_it_matters"]
        assert finding["failure_scenario"]
        assert analysis.json()["result"]["summary"]["priority_actions"]
        debug = client.post("/api/debug", json={
            "repository_id": repository_id,
            "problem": "Login returns HTTP 500 when the password is incorrect",
        })
        assert debug.status_code == 201
        assert debug.json()["result"]["verification"]["status"] == "unable_to_verify"
        result = debug.json()["result"]
        hypothesis = result["hypotheses"][0]
        assert hypothesis["file"] == "store/auth.py"
        assert result["explanation"]["headline"] == "Generic exception raised"
        assert result["explanation"]["code_excerpt"]
        assert any(line["highlighted"] for line in result["explanation"]["code_excerpt"])
        assert result["explanation"]["fact_vs_inference"]["observed"]
        reports = client.get("/api/reports", params={"repository_id": repository_id})
        assert reports.status_code == 200
        assert {item["kind"] for item in reports.json()} >= {"analysis", "debug"}
        assert client.get("/api/tests", params={"repository_id": repository_id}).status_code == 200


def test_failed_import_cannot_analyze_backend_working_directory():
    with TestClient(app) as client:
        failed = client.post("/api/repositories", json={"local_path": str(SAMPLE / "missing")})
        assert failed.status_code == 422
        repository_id = client.get("/api/repositories").json()[0]["id"]
        analysis = client.post("/api/analysis", json={"repository_id": repository_id})
        assert analysis.status_code == 409


def test_workspace_paths_are_removed_from_historical_results():
    result = _sanitize_workspace_paths({
        "file": ".repowise/workspaces/3/store/auth.py",
        "detail": "Root cause at .repowise/workspaces/3/store/auth.py:22",
    })
    assert result["file"] == "store/auth.py"
    assert result["detail"] == "Root cause at store/auth.py:22"


def test_supported_candidate_uses_before_after_execution(monkeypatch):
    issue = next(item for item in analyze_repository(SAMPLE) if item.title == "Generic exception raised")
    generated = DebuggingWorkflow._regression_test(SAMPLE, issue)
    assert generated["status"] == "generated"
    outcomes = iter([
        {"status": "failed", "exit_code": 1, "duration_ms": 10, "stdout": "1 failed", "stderr": ""},
        {"status": "passed", "exit_code": 0, "duration_ms": 12, "stdout": "3 passed", "stderr": ""},
    ])
    monkeypatch.setattr(agents, "run_tests", lambda root, runner: next(outcomes))
    verification, results = DebuggingWorkflow._verify_candidate(SAMPLE, issue, generated)
    assert verification["status"] == "verified"
    assert results["before"]["status"] == "failed"
    assert results["after"]["status"] == "passed"


def test_test_output_explains_collection_system_exit():
    output = ('9 passed, 0 failed\n3 warnings, 5 errors\n'
              'File "/workspace/tests/test_packaging.py", line 78, in <module>\n'
              'sys.exit(1 if FAIL else 0)\nSystemExit: 0\nINTERNALERROR> collection aborted')
    summary = summarize_test_output(output, 3)
    assert summary["outcome"] == "collection_error"
    assert summary["passed"] == 9
    assert summary["errors"] == 5
    assert "sys.exit" in summary["cause"]
