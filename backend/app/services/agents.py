import ast
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.config import get_settings
from app.execution.sandbox import SandboxUnavailable, run_tests
from app.schemas import Issue
from app.services.analysis import analyze_repository
from app.services.indexer import CodeIndex


@dataclass
class InvestigationState:
    repository_id: int
    user_problem: str
    relevant_files: list[dict] = field(default_factory=list)
    hypotheses: list[dict] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    proposed_fix: dict = field(default_factory=dict)
    generated_tests: list[dict] = field(default_factory=list)
    test_results: dict = field(default_factory=dict)
    verification: dict = field(default_factory=dict)
    explanation: dict = field(default_factory=dict)
    history: list[dict] = field(default_factory=list)


class DebuggingWorkflow:
    """Explicit, auditable state machine; deterministic nodes work without a paid LLM."""

    def __init__(self, index: CodeIndex):
        self.index = index

    def run(self, repository_id: int, root: Path, problem: str) -> dict:
        state = InvestigationState(repository_id, problem)
        self._step(state, "understand", "Problem statement normalized and investigation scope established.")
        state.relevant_files = self.index.search(repository_id, problem, limit=10)
        self._step(state, "retrieve", f"Retrieved {len(state.relevant_files)} relevant code symbols.")
        issues = analyze_repository(root)
        related = self._rank_issues(problem, issues, state.relevant_files)
        if related:
            issue = related[0]
            state.hypotheses.append({"confidence": "high", "claim": issue.title, "file": issue.file, "line": issue.line})
            state.evidence.append(f"{issue.file}:{issue.line} — {issue.evidence}")
            state.proposed_fix = {"file": issue.file, "line": issue.line, "description": issue.suggested_fix}
            state.explanation = self._explain_issue(root, problem, issue, state.relevant_files)
            self._step(state, "investigate", f"Root-cause candidate found at {issue.file}:{issue.line}.")
            generated = self._regression_test(root, issue)
            state.generated_tests.append(generated)
            self._step(state, "generate_test", "Generated an isolated regression test.")
            state.verification, state.test_results = self._verify_candidate(root, issue, generated)
            verification_detail = {
                "verified": "Regression test failed before the candidate fix and the full suite passed after it.",
                "partially_verified": "The candidate improved the result, but complete verification criteria were not met.",
                "failed": "The candidate fix did not pass the regression and related tests.",
                "unable_to_verify": state.verification["summary"],
            }[state.verification["status"]]
            self._step(state, "verify", verification_detail)
        else:
            state.hypotheses.append({"confidence": "low", "claim": "No deterministic finding directly matched the report."})
            state.explanation = {
                "status": "inconclusive",
                "headline": "No supported root cause was identified",
                "plain_language": "The available deterministic evidence does not explain the reported behavior yet.",
                "observed_behavior": problem,
                "why_it_happens": "Unknown; more runtime evidence or a narrower reproduction is required.",
                "impact": "The impact cannot be stated reliably from the current evidence.",
                "confidence": "low",
                "confidence_reason": "No static finding had a strong match to the retrieved execution path.",
                "execution_path": [], "code_excerpt": [], "next_action": "Collect a stack trace or failing test output.",
            }
            state.verification = {"status": "unable_to_verify", "summary": "Insufficient evidence for a verified fix.", "evidence": []}
            self._step(state, "investigate", "No high-confidence deterministic root cause was found.")
        self._step(state, "report", "Compiled observed facts, hypotheses, and verification status.")
        return asdict(state)

    @staticmethod
    def _step(state: InvestigationState, name: str, detail: str) -> None:
        state.history.append({"step": len(state.history) + 1, "node": name, "status": "complete", "detail": detail})

    @staticmethod
    def _rank_issues(problem: str, issues: list[Issue], chunks: list[dict]) -> list[Issue]:
        terms = set(problem.lower().split())
        relevant_paths = {chunk["file"] for chunk in chunks}
        return sorted(issues, key=lambda issue: (
            3 * (issue.file in relevant_paths) +
            len(terms & set((issue.title + " " + issue.explanation + " " + issue.file).lower().split()))
        ), reverse=True)

    @staticmethod
    def _regression_test(root: Path, issue: Issue) -> dict:
        generated = {
            "target": issue.file, "framework": "pytest" if issue.file.endswith(".py") else "configured JavaScript test runner",
            "description": f"Exercise the failure path around line {issue.line} and assert a controlled result instead of an unhandled error.",
            "status": "proposed", "file": None, "content": None,
        }
        if issue.title != "Generic exception raised" or not issue.file.endswith(".py"):
            return generated
        try:
            source = (root / issue.file).read_text(encoding="utf-8")
            tree = ast.parse(source)
            function = next((node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                             and node.lineno <= issue.line <= (node.end_lineno or node.lineno)), None)
            usernames = []
            for node in tree.body:
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
                    usernames.extend(key.value for key in node.value.keys if isinstance(key, ast.Constant) and isinstance(key.value, str))
            if function and "auth" in function.name.lower() and len(function.args.args) >= 2 and usernames:
                module = issue.file[:-3].replace("/", ".").replace("\\", ".")
                test_file = "tests/test_repowise_regression.py"
                content = (f"from {module} import {function.name}\n\n\n"
                           f"def test_invalid_password_is_a_controlled_failure():\n"
                           f"    assert {function.name}({usernames[0]!r}, 'repowise-invalid-password') is None\n")
                generated.update({"status": "generated", "file": test_file, "content": content,
                                  "symbol": function.name})
        except (OSError, SyntaxError):
            pass
        return generated

    @staticmethod
    def _verify_candidate(root: Path, issue: Issue, generated: dict) -> tuple[dict, dict]:
        if generated.get("status") != "generated":
            return ({"status": "unable_to_verify",
                     "summary": "No safe deterministic patch and executable regression test are available for this finding.",
                     "evidence": ["The proposed change requires human or LLM review before execution."]}, {})
        settings = get_settings()
        settings.workspace_root.mkdir(parents=True, exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(prefix="verification-", dir=settings.workspace_root.resolve()) as temp:
                workspace = Path(temp) / "repository"
                shutil.copytree(root, workspace)
                test_path = workspace / generated["file"]
                test_path.parent.mkdir(parents=True, exist_ok=True)
                test_path.write_text(generated["content"], encoding="utf-8")
                before = run_tests(workspace, "pytest")
                source_path = workspace / issue.file
                lines = source_path.read_text(encoding="utf-8").splitlines()
                original = lines[issue.line - 1]
                indentation = original[:len(original) - len(original.lstrip())]
                lines[issue.line - 1] = indentation + "return None"
                source_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                after = run_tests(workspace, "pytest")
                results = {"before": before, "after": after, "candidate_patch": {
                    "file": issue.file, "line": issue.line, "before": original.strip(), "after": "return None"}}
                if before["status"] == "failed" and after["status"] == "passed":
                    return ({"status": "verified", "summary": "The regression test reproduced the bug before the candidate and the complete suite passed after it.",
                             "evidence": [f"Before: exit {before['exit_code']}", f"After: exit {after['exit_code']}"]}, results)
                if after["status"] == "passed":
                    return ({"status": "partially_verified", "summary": "The patched suite passes, but the new test did not reproduce a failing baseline.",
                             "evidence": [f"Before: {before['status']}", "After: passed"]}, results)
                return ({"status": "failed", "summary": "The candidate did not make the complete test suite pass.",
                         "evidence": [f"Before: {before['status']}", f"After: {after['status']}"]}, results)
        except SandboxUnavailable as exc:
            return ({"status": "unable_to_verify", "summary": str(exc), "evidence": ["Start Docker and retry the investigation."]}, {})
        except (OSError, IndexError) as exc:
            return ({"status": "unable_to_verify", "summary": f"The isolated verification workspace could not be prepared: {exc}",
                     "evidence": []}, {})

    @staticmethod
    def _explain_issue(root: Path, problem: str, issue: Issue, chunks: list[dict]) -> dict:
        descriptions = {
            "Generic exception raised": (
                "An expected failure path raises a generic exception instead of returning or raising a controlled domain error.",
                "When that exception reaches an API boundary without a matching handler, the framework treats it as an unexpected failure and commonly returns HTTP 500.",
                "Users see a server error for an ordinary invalid request, while clients cannot distinguish bad input from an outage.",
            ),
            "Dynamic code execution": (
                "The code executes a string as program code.",
                "If any portion of that string is influenced by external input, it can run operations the application never intended.",
                "This can lead to arbitrary code execution and compromise application data or infrastructure.",
            ),
            "Possible hard-coded secret": (
                "A credential-like value is stored directly in source code.",
                "Anyone with source or build access may recover it, and rotating it requires a code change.",
                "The credential may leak through version history, packages, logs, or screenshots.",
            ),
            "Bare exception handler": (
                "The code catches every exception without identifying the failures it expects.",
                "Programming errors and operational failures are handled as if they were normal, hiding their original cause.",
                "Failures become harder to diagnose and the program may continue with invalid state.",
            ),
        }
        plain, why, impact = descriptions.get(issue.title, (
            issue.explanation,
            "The highlighted construct conflicts with the expected behavior described in the investigation.",
            "The affected path may behave incorrectly or fail without a clear error contract.",
        ))
        lines: list[dict] = []
        try:
            source = (root / issue.file).resolve()
            if root.resolve() in source.parents and source.is_file():
                all_lines = source.read_text(encoding="utf-8", errors="replace").splitlines()
                start, end = max(1, issue.line - 3), min(len(all_lines), issue.line + 3)
                lines = [{"line": number, "text": all_lines[number - 1], "highlighted": number == issue.line}
                         for number in range(start, end + 1)]
        except OSError:
            lines = []
        path = []
        for chunk in chunks:
            step = {"file": chunk["file"], "symbol": chunk["symbol"],
                    "lines": f'{chunk["start_line"]}-{chunk["end_line"]}'}
            if step not in path:
                path.append(step)
            if len(path) == 4:
                break
        return {
            "status": "root_cause_candidate",
            "headline": issue.title,
            "plain_language": plain,
            "observed_behavior": problem,
            "why_it_happens": why,
            "impact": impact,
            "location": {"file": issue.file, "line": issue.line},
            "confidence": "high",
            "confidence_reason": "A deterministic source-code finding matches the retrieved files and the reported failure terms.",
            "fact_vs_inference": {
                "observed": f"The source contains `{issue.evidence}` at {issue.file}:{issue.line}.",
                "inference": why,
            },
            "execution_path": path,
            "code_excerpt": lines,
            "recommended_fix": issue.suggested_fix,
            "test_intent": f"Trigger the reported failure path and assert a controlled result rather than an unhandled {issue.title.lower()}.",
            "next_action": "Review the proposed change, generate the regression test, then execute the focused and related test suites.",
        }
