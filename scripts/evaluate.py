import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.agents import DebuggingWorkflow
from app.services.indexer import CodeIndex


def main() -> None:
    sample = ROOT / "examples" / "sample-python-project"
    index = CodeIndex()
    chunks = index.index(1, sample)
    started = time.monotonic()
    result = DebuggingWorkflow(index).run(1, sample, "Login fails with HTTP 500 when the password is incorrect")
    expected = any(h.get("file") == "store/auth.py" and h.get("line") == 22 for h in result["hypotheses"])
    metrics = {
        "cases": 1, "indexed_chunks": chunks, "bug_detection_rate": float(bool(result["hypotheses"])),
        "correct_root_cause_rate": float(expected), "test_generation_success": float(bool(result["generated_tests"])),
        "verification_success": float(result["verification"]["status"] == "verified"),
        "average_execution_ms": round((time.monotonic() - started) * 1000, 2),
    }
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()

