import ast
import re
from collections import Counter
from pathlib import Path

from app.schemas import Issue
from app.services.repository import _safe_files


def analyze_repository(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    for path, rel, _ in _safe_files(root):
        if path.suffix == ".py":
            issues.extend(_python_issues(path, rel))
        elif path.suffix in {".js", ".jsx", ".ts", ".tsx"}:
            issues.extend(_javascript_issues(path, rel))
    return issues


def explain_finding(root: Path, issue: Issue) -> dict:
    scenarios = {
        "Dynamic code execution": {
            "why_it_matters": "This operation treats data as executable program code, crossing a critical trust boundary.",
            "failure_scenario": "If an attacker can influence the evaluated value, they may read data, alter application behavior, or execute commands with the service's permissions.",
            "recommended_test": "Pass a harmless code-like payload through the input boundary and assert it is rejected without execution.",
        },
        "Generic exception raised": {
            "why_it_matters": "Expected business failures become indistinguishable from unexpected server faults.",
            "failure_scenario": "A normal invalid input reaches this line, raises an unhandled exception, and is returned to the caller as HTTP 500.",
            "recommended_test": "Trigger this branch and assert the documented error result and status code.",
        },
        "Possible hard-coded secret": {
            "why_it_matters": "Credentials in source are easy to copy and remain recoverable from version history.",
            "failure_scenario": "A repository, build artifact, or log is shared and exposes a reusable credential.",
            "recommended_test": "Add secret scanning to CI and assert configuration fails safely when the environment value is absent.",
        },
        "Bare exception handler": {
            "why_it_matters": "Unexpected programming and infrastructure failures are silently treated as known errors.",
            "failure_scenario": "A defect is swallowed, execution continues with incomplete state, and the original traceback is lost.",
            "recommended_test": "Raise an unexpected exception in the protected block and assert it remains observable.",
        },
    }
    detail = scenarios.get(issue.title, {
        "why_it_matters": issue.explanation,
        "failure_scenario": "The highlighted path may produce behavior that violates its caller's expected contract.",
        "recommended_test": "Exercise the highlighted branch and assert its expected contract.",
    })
    excerpt: list[dict] = []
    try:
        path = (root / issue.file).resolve()
        if root.resolve() in path.parents and path.is_file():
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            start, end = max(1, issue.line - 2), min(len(lines), issue.line + 2)
            excerpt = [{"line": number, "text": lines[number - 1], "highlighted": number == issue.line}
                       for number in range(start, end + 1)]
    except OSError:
        pass
    return {**issue.model_dump(), **detail, "confidence": "high", "confidence_basis": "Detected directly from the parsed source tree.",
            "code_excerpt": excerpt}


def summarize_findings(issues: list[dict], profile: dict) -> dict:
    order = {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1}
    ranked = sorted(issues, key=lambda item: order.get(item["severity"], 0), reverse=True)
    highest = ranked[0]["severity"] if ranked else "none"
    source_count, test_count = profile.get("source_files", 0), profile.get("test_files", 0)
    return {
        "risk_level": highest,
        "executive_summary": (
            f"The scan found {len(issues)} actionable finding(s). The highest observed severity is {highest}."
            if issues else "No supported deterministic findings were detected in the scanned source files."
        ),
        "affected_files": sorted({item["file"] for item in issues}),
        "categories": dict(Counter(item["category"] for item in issues)),
        "priority_actions": [{"title": item["title"], "file": item["file"], "line": item["line"],
                              "action": item["suggested_fix"]} for item in ranked[:3]],
        "test_posture": {
            "source_files": source_count, "test_files": test_count,
            "ratio": round(test_count / source_count, 2) if source_count else 0,
            "assessment": "No test files were detected; every fix requires a new regression test." if not test_count
                          else "Tests exist, but each highlighted failure path still needs a focused regression test.",
        },
    }


def _python_issues(path: Path, rel: str) -> list[Issue]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    issues: list[Issue] = []
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [Issue(
            severity="high", category="correctness", title="Syntax error",
            explanation=str(exc), file=rel, line=exc.lineno or 1,
            evidence=exc.text or "", suggested_fix="Correct the invalid Python syntax.",
        )]
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            issues.append(Issue(
                severity="medium", category="reliability", title="Bare exception handler",
                explanation="Catching every exception can conceal programming errors and cancellation signals.",
                file=rel, line=node.lineno, evidence="except:",
                suggested_fix="Catch the narrow expected exception type.",
            ))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
            issues.append(Issue(
                severity="critical", category="security", title="Dynamic code execution",
                explanation="Untrusted data reaching this call can execute arbitrary code.", file=rel,
                line=node.lineno, evidence=node.func.id + "(...)",
                suggested_fix="Replace with a constrained parser.",
            ))
        if (
            isinstance(node, ast.Raise)
            and isinstance(node.exc, ast.Call)
            and isinstance(node.exc.func, ast.Name)
            and node.exc.func.id == "Exception"
        ):
            issues.append(Issue(
                severity="medium", category="error-handling", title="Generic exception raised",
                explanation="A generic exception obscures the failure contract and often becomes an HTTP 500.",
                file=rel, line=node.lineno, evidence="raise Exception(...)",
                suggested_fix="Raise a domain-specific exception and map it to an expected response.",
            ))
    for lineno, line in enumerate(text.splitlines(), 1):
        if re.search(r"(?:password|secret|api_key|token)\s*=\s*['\"][^'\"]+['\"]", line, re.I):
            issues.append(Issue(
                severity="high", category="security", title="Possible hard-coded secret",
                explanation="Credentials should not be stored in source code.", file=rel, line=lineno,
                evidence=line.strip()[:160],
                suggested_fix="Load the value from a secret manager or environment variable.",
            ))
    return issues


def _javascript_issues(path: Path, rel: str) -> list[Issue]:
    issues: list[Issue] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
        if "eval(" in line:
            issues.append(Issue(
                severity="critical", category="security", title="Dynamic code execution",
                explanation="eval executes strings as code.", file=rel, line=lineno,
                evidence=line.strip()[:160], suggested_fix="Use a safe parser or explicit dispatch table.",
            ))
        if re.search(r"console\.log\(.*(?:password|token|secret)", line, re.I):
            issues.append(Issue(
                severity="high", category="security", title="Sensitive value logged",
                explanation="Secrets may be exposed through application logs.", file=rel, line=lineno,
                evidence=line.strip()[:160], suggested_fix="Remove sensitive values from logs.",
            ))
    return issues
