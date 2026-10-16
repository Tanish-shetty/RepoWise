import logging
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import AnalysisRun, Repository, TestRun, get_db
from app.execution.sandbox import SandboxUnavailable, run_tests, summarize_test_output
from app.schemas import (DebugRequest, RepositoryCreate, RepositoryView, RunRequest, RunView,
                         SearchRequest, TestExecuteRequest, TestGenerateRequest)
from app.services.agents import DebuggingWorkflow
from app.services.analysis import analyze_repository, explain_finding, summarize_findings
from app.services.indexer import code_index
from app.services.repository import RepositoryError, prepare_repository, profile_repository, repository_tree

router = APIRouter(prefix="/api")
log = logging.getLogger("repowise.api")


def _sanitize_workspace_paths(value):
    """Keep private workspace locations out of API responses, including historical runs."""
    if isinstance(value, str):
        return re.sub(r"\S*?[\\/]?\.repowise[\\/]workspaces[\\/]\d+[\\/]", "", value)
    if isinstance(value, list):
        return [_sanitize_workspace_paths(item) for item in value]
    if isinstance(value, dict):
        return {key: _sanitize_workspace_paths(item) for key, item in value.items()}
    return value


def _repository(db: Session, repository_id: int) -> Repository:
    repository = db.get(Repository, repository_id)
    if not repository:
        raise HTTPException(404, "Repository not found")
    return repository


def _repository_root(repository: Repository, *, require_scanned: bool = False) -> Path:
    if repository.status == "failed" or not repository.local_path:
        detail = repository.profile.get("error") if repository.profile else None
        raise HTTPException(409, detail or "Repository import failed; import it again before running analysis")
    root = Path(repository.local_path).resolve()
    if not root.is_dir():
        raise HTTPException(409, "Repository workspace is unavailable; import it again")
    if require_scanned and repository.status != "ready":
        raise HTTPException(409, "Repository must be scanned before this operation")
    return root


@router.post("/repositories", response_model=RepositoryView, status_code=201)
def create_repository(payload: RepositoryCreate, db: Session = Depends(get_db)):
    source = str(payload.github_url) if payload.github_url else str(Path(payload.local_path or "").resolve())
    repository = Repository(name=Path(source.rstrip("/")).stem.replace(".git", ""), source=source, local_path="", status="pending")
    db.add(repository); db.commit(); db.refresh(repository)
    try:
        root = prepare_repository(source, repository.id)
        repository.local_path = str(root)
        repository.status = "imported"
        db.commit(); db.refresh(repository)
        return repository
    except RepositoryError as exc:
        repository.status = "failed"; repository.profile = {"error": str(exc)}; db.commit()
        raise HTTPException(422, str(exc)) from exc


@router.get("/repositories", response_model=list[RepositoryView])
def list_repositories(db: Session = Depends(get_db)):
    return list(db.scalars(select(Repository).order_by(Repository.created_at.desc())))


@router.get("/repositories/{repository_id}", response_model=RepositoryView)
def get_repository(repository_id: int, db: Session = Depends(get_db)):
    return _repository(db, repository_id)


@router.post("/repositories/{repository_id}/scan", response_model=RepositoryView)
def scan_repository(repository_id: int, db: Session = Depends(get_db)):
    repository = _repository(db, repository_id)
    try:
        root = _repository_root(repository)
        profile, _ = profile_repository(root)
        profile["indexed_chunks"] = code_index.index(repository.id, root)
        repository.profile = profile; repository.status = "ready"
        db.commit(); db.refresh(repository)
        return repository
    except (OSError, RepositoryError) as exc:
        repository.status = "failed"; db.commit()
        raise HTTPException(422, f"Scan failed: {exc}") from exc


@router.get("/repositories/{repository_id}/structure")
def structure(repository_id: int, db: Session = Depends(get_db)):
    repository = _repository(db, repository_id)
    return {"repository_id": repository.id, "files": repository_tree(_repository_root(repository, require_scanned=True))}


@router.post("/search")
def search(payload: SearchRequest, db: Session = Depends(get_db)):
    repository = _repository(db, payload.repository_id)
    root = _repository_root(repository, require_scanned=True)
    if repository.id not in code_index._chunks:
        code_index.index(repository.id, root)
    return {"results": code_index.search(repository.id, payload.query, limit=payload.limit,
                                           language=payload.language, path_prefix=payload.path_prefix)}


@router.post("/analysis", response_model=RunView, status_code=201)
def create_analysis(payload: RunRequest, db: Session = Depends(get_db)):
    repository = _repository(db, payload.repository_id)
    root = _repository_root(repository, require_scanned=True)
    issues = [explain_finding(root, item) for item in analyze_repository(root)]
    result = {"issues": issues, "summary": {
        "total": len(issues),
        "high_or_critical": sum(i["severity"] in {"high", "critical"} for i in issues),
        **summarize_findings(issues, repository.profile),
    }}
    run = AnalysisRun(repository_id=repository.id, kind="analysis", status="completed", result=result)
    db.add(run); db.commit(); db.refresh(run)
    return run


@router.post("/debug", response_model=RunView, status_code=201)
def debug(payload: DebugRequest, db: Session = Depends(get_db)):
    repository = _repository(db, payload.repository_id)
    root = _repository_root(repository, require_scanned=True)
    if repository.id not in code_index._chunks:
        code_index.index(repository.id, root)
    result = DebuggingWorkflow(code_index).run(repository.id, root, payload.problem)
    run = AnalysisRun(repository_id=repository.id, kind="debug", status="completed", request=payload.problem, result=result)
    db.add(run); db.commit(); db.refresh(run)
    return run


@router.get("/analysis/{run_id}", response_model=RunView)
@router.get("/debug/{run_id}", response_model=RunView)
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(AnalysisRun, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return {"id": run.id, "repository_id": run.repository_id, "kind": run.kind,
            "status": run.status, "request": run.request,
            "result": _sanitize_workspace_paths(run.result)}


@router.post("/tests/generate", response_model=RunView, status_code=201)
def generate_test(payload: TestGenerateRequest, db: Session = Depends(get_db)):
    repository = _repository(db, payload.repository_id)
    framework = "pytest" if payload.target.endswith(".py") else "configured JavaScript test runner"
    result = {"generated_tests": [{"target": payload.target, "framework": framework,
        "description": payload.behavior, "status": "proposed"}],
        "notice": "The proposal is kept separate from repository files until explicitly reviewed."}
    run = AnalysisRun(repository_id=repository.id, kind="test_generation", status="completed",
                      request=payload.behavior, result=result)
    db.add(run); db.commit(); db.refresh(run)
    return run


@router.post("/tests/run", status_code=201)
def execute_tests(payload: TestExecuteRequest, db: Session = Depends(get_db)):
    repository = _repository(db, payload.repository_id)
    try:
        result = run_tests(_repository_root(repository, require_scanned=True), payload.runner)
        output = (result.get("stdout", "") + "\n" + result.get("stderr", "")).strip()
        test_run = TestRun(repository_id=repository.id, status=result["status"],
                           exit_code=result["exit_code"], duration_ms=result["duration_ms"], output=output)
        db.add(test_run); db.commit(); db.refresh(test_run)
        return {"id": test_run.id, "repository_id": repository.id, **result,
                "summary": summarize_test_output(output, test_run.exit_code)}
    except SandboxUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/tests")
def list_test_runs(repository_id: int | None = None, db: Session = Depends(get_db)):
    statement = select(TestRun)
    if repository_id is not None:
        statement = statement.where(TestRun.repository_id == repository_id)
    statement = statement.order_by(TestRun.id.desc()).limit(100)
    runs = list(db.scalars(statement))
    return [{"id": run.id, "repository_id": run.repository_id, "status": run.status,
             "exit_code": run.exit_code, "duration_ms": run.duration_ms, "output": run.output,
             "summary": summarize_test_output(run.output, run.exit_code)}
            for run in runs]


@router.get("/tests/{test_run_id}")
def get_test_run(test_run_id: int, db: Session = Depends(get_db)):
    run = db.get(TestRun, test_run_id)
    if not run:
        raise HTTPException(404, "Test run not found")
    return {"id": run.id, "repository_id": run.repository_id, "status": run.status,
            "exit_code": run.exit_code, "duration_ms": run.duration_ms, "output": run.output,
            "summary": summarize_test_output(run.output, run.exit_code)}


@router.get("/reports")
def list_reports(repository_id: int | None = None, db: Session = Depends(get_db)):
    statement = select(AnalysisRun)
    if repository_id is not None:
        statement = statement.where(AnalysisRun.repository_id == repository_id)
    statement = statement.order_by(AnalysisRun.created_at.desc()).limit(100)
    runs = list(db.scalars(statement))
    repositories = {item.id: item for item in db.scalars(select(Repository))}
    return [{"id": run.id, "repository_id": run.repository_id,
             "repository_name": repositories.get(run.repository_id).name if repositories.get(run.repository_id) else "Unknown",
             "kind": run.kind, "status": run.status, "request": run.request,
             "created_at": run.created_at.isoformat(),
             "verification": _sanitize_workspace_paths(run.result.get("verification")),
             "finding_count": len(run.result.get("issues", []))}
            for run in runs]


@router.get("/reports/{run_id}")
def report(run_id: int, db: Session = Depends(get_db)):
    run = db.get(AnalysisRun, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    repository = _repository(db, run.repository_id)
    return {"id": run.id, "repository": repository.profile, "kind": run.kind,
            "observed_facts": _sanitize_workspace_paths(run.result.get("evidence", run.result.get("issues", []))),
            "ai_hypotheses": _sanitize_workspace_paths(run.result.get("hypotheses", [])),
            "verification": _sanitize_workspace_paths(run.result.get("verification", {"status": "not_applicable"})),
            "result": _sanitize_workspace_paths(run.result)}
