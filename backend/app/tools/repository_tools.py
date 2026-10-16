from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field

from app.services.indexer import CodeIndex
from app.services.repository import repository_tree


class ToolResult(BaseModel):
    ok: bool
    data: Any = None
    error: str | None = None


class ReadFileInput(BaseModel):
    path: str = Field(min_length=1, max_length=500)
    start_line: int = Field(default=1, ge=1)
    end_line: int = Field(default=200, ge=1, le=1000)


class RepositoryTools:
    """Validated, bounded tools exposed to agents; intentionally no arbitrary shell."""

    def __init__(self, root: Path, repository_id: int, index: CodeIndex):
        self.root, self.repository_id, self.index = root.resolve(), repository_id, index
        self.registry: dict[str, Callable] = {
            "list_files": self.list_files,
            "read_file": self.read_file,
            "search_code": self.search_code,
        }

    def _path(self, relative: str) -> Path:
        candidate = (self.root / relative).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise ValueError("Path leaves repository root")
        return candidate

    def list_files(self) -> ToolResult:
        return ToolResult(ok=True, data=repository_tree(self.root))

    def read_file(self, payload: ReadFileInput) -> ToolResult:
        try:
            path = self._path(payload.path)
            if not path.is_file() or path.stat().st_size > 512 * 1024:
                return ToolResult(ok=False, error="File is missing or exceeds the read limit")
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            return ToolResult(ok=True, data={"path": payload.path, "start_line": payload.start_line,
                "end_line": min(payload.end_line, len(lines)),
                "content": "\n".join(lines[payload.start_line - 1:payload.end_line])})
        except (OSError, ValueError) as exc:
            return ToolResult(ok=False, error=str(exc))

    def search_code(self, query: str, limit: int = 8) -> ToolResult:
        return ToolResult(ok=True, data=self.index.search(self.repository_id, query, limit=min(limit, 20)))

