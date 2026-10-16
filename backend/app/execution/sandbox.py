import shutil
import subprocess
import time
import os
import re
from pathlib import Path

from app.config import get_settings


class SandboxUnavailable(RuntimeError):
    pass


ALLOWED_TEST_COMMANDS = {
    "pytest": ["pytest", "-q"],
    "npm_test": ["npm", "test", "--", "--runInBand"],
}


def summarize_test_output(output: str, exit_code: int) -> dict:
    def last_count(label: str) -> int:
        matches = re.findall(rf"(\d+)\s+{label}\b", output, re.IGNORECASE)
        return int(matches[-1]) if matches else 0

    passed, failed = last_count("passed"), last_count("failed")
    errors, skipped, warnings = last_count("errors?"), last_count("skipped"), last_count("warnings?")
    if "INTERNALERROR" in output or exit_code == 3:
        outcome = "collection_error"
        headline = "Pytest could not finish collecting the test suite"
    elif exit_code == 124:
        outcome = "timeout"
        headline = "The test run exceeded its execution timeout"
    elif exit_code == 0:
        outcome = "passed"
        headline = "All collected tests passed"
    elif failed:
        outcome = "test_failures"
        headline = f"{failed} test assertion{'s' if failed != 1 else ''} failed"
    else:
        outcome = "execution_error"
        headline = "The test process failed before producing normal results"
    cause = ""
    action = "Open the raw output for the complete runner log."
    if "SystemExit" in output and "sys.exit" in output:
        location = re.findall(r'File "([^"]+)", line (\d+)', output)
        shown = f"{location[-1][0]}:{location[-1][1]}" if location else "a collected test module"
        cause = f"{shown} calls sys.exit() while pytest imports the module, aborting collection."
        action = "Move script execution behind `if __name__ == '__main__':` or convert it into pytest assertions."
    elif "ModuleNotFoundError" in output:
        modules = re.findall(r"No module named ['\"]([^'\"]+)", output)
        cause = f"A required dependency is missing: {modules[-1]}." if modules else "A required Python dependency is missing."
        action = "Install repository dependencies in a dedicated sandbox image before running the suite."
    elif outcome == "test_failures":
        cause = "One or more collected tests completed with assertion failures."
        action = "Inspect the first failure and trace it to the affected source path."
    return {"outcome": outcome, "headline": headline, "passed": passed, "failed": failed,
            "errors": errors, "skipped": skipped, "warnings": warnings,
            "cause": cause, "recommended_action": action,
            "completed_tests": passed + failed}


def run_tests(root: Path, runner: str) -> dict:
    if runner not in ALLOWED_TEST_COMMANDS:
        raise ValueError("Unsupported test runner")
    if not shutil.which("docker"):
        raise SandboxUnavailable("Docker is unavailable; repository code was not executed on the host")
    settings = get_settings()
    image = "repowise-sandbox-python:latest" if runner == "pytest" else "repowise-sandbox-node:latest"
    command = ALLOWED_TEST_COMMANDS[runner]
    docker_cmd = ["docker", "run", "--rm", "--network", "none", "--cpus", "1",
                  "--memory", "512m", "--pids-limit", "128", "--read-only",
                  "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m"]
    container_id = os.getenv("HOSTNAME") if Path("/.dockerenv").exists() else None
    if container_id:
        docker_cmd.extend(["--volumes-from", f"{container_id}:ro", "-w", str(root.resolve())])
    else:
        docker_cmd.extend(["-v", f"{root.resolve()}:/workspace:ro", "-w", "/workspace"])
    docker_cmd.extend([image, *command])
    started = time.monotonic()
    try:
        result = subprocess.run(docker_cmd, capture_output=True, text=True,
                                timeout=settings.sandbox_timeout, check=False)
        infrastructure_error = (result.stderr + result.stdout).lower()
        if result.returncode == 125 or any(marker in infrastructure_error for marker in (
            "cannot connect to the docker daemon", "failed to connect to the docker api",
            "no such image", "is the docker daemon running", "permission denied while trying to connect to the docker api",
        )):
            raise SandboxUnavailable("Docker sandbox is unavailable; start Docker and build the sandbox images")
        return {"status": "passed" if result.returncode == 0 else "failed", "exit_code": result.returncode,
                "duration_ms": int((time.monotonic() - started) * 1000),
                "stdout": result.stdout[-12000:], "stderr": result.stderr[-12000:]}
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "exit_code": 124,
                "duration_ms": int((time.monotonic() - started) * 1000), "stdout": "", "stderr": "Execution timed out"}
