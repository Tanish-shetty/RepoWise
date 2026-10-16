import ast
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from app.services.repository import EXTENSIONS, _safe_files


@dataclass
class CodeChunk:
    repository_id: int
    file: str
    language: str
    symbol: str
    start_line: int
    end_line: int
    chunk_type: str
    imports: list[str]
    content: str


class CodeIndex:
    """Replaceable in-process vector index using sparse hashed token vectors."""

    def __init__(self) -> None:
        self._chunks: dict[int, list[CodeChunk]] = {}
        self._vectors: dict[int, list[Counter[str]]] = {}

    @staticmethod
    def _vector(text: str) -> Counter[str]:
        normalized = re.sub(r"([a-z])([A-Z])", r"\1 \2", text).replace("_", " ").lower()
        tokens = re.findall(r"[a-z][a-z0-9]{1,}", normalized)
        synonyms = {
            "login": ("auth", "authenticate", "authentication"),
            "bug": ("error", "failure", "exception"),
            "failing": ("failure", "error", "exception"),
            "test": ("pytest", "spec", "assert"),
        }
        expanded = list(tokens)
        for token in tokens:
            expanded.extend(synonyms.get(token, ()))
        return Counter(expanded)

    def index(self, repository_id: int, root: Path) -> int:
        chunks: list[CodeChunk] = []
        for path, rel, _ in _safe_files(root):
            language = EXTENSIONS.get(path.suffix.lower())
            if not language:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            chunks.extend(chunk_file(repository_id, rel, language, text))
        self._chunks[repository_id] = chunks
        self._vectors[repository_id] = [self._vector(c.content + " " + c.symbol + " " + c.file) for c in chunks]
        return len(chunks)

    def search(self, repository_id: int, query: str, *, limit: int = 8,
               language: str | None = None, path_prefix: str | None = None) -> list[dict]:
        query_vec = self._vector(query)
        results = []
        for chunk, vector in zip(self._chunks.get(repository_id, []), self._vectors.get(repository_id, [])):
            if language and chunk.language.lower() != language.lower():
                continue
            if path_prefix and not chunk.file.startswith(path_prefix):
                continue
            shared = set(query_vec) & set(vector)
            dot = sum(query_vec[t] * vector[t] for t in shared)
            denom = math.sqrt(sum(v * v for v in query_vec.values()) * sum(v * v for v in vector.values())) or 1
            semantic = dot / denom
            symbol_bonus = 0.35 if any(t in chunk.symbol.lower() for t in query_vec) else 0
            path_bonus = 0.2 if any(t in chunk.file.lower() for t in query_vec) else 0
            score = semantic + symbol_bonus + path_bonus
            if score > 0:
                results.append({**asdict(chunk), "score": round(score, 4)})
        return sorted(results, key=lambda item: item["score"], reverse=True)[:limit]


def chunk_file(repository_id: int, rel: str, language: str, text: str) -> list[CodeChunk]:
    if language == "Python":
        try:
            tree = ast.parse(text)
            imports = [ast.unparse(n) for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
            chunks = []
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    lines = text.splitlines()
                    chunks.append(CodeChunk(repository_id, rel, language, node.name, node.lineno,
                                            node.end_lineno or node.lineno, node.__class__.__name__.lower(),
                                            imports, "\n".join(lines[node.lineno - 1:node.end_lineno])))
            if chunks:
                return chunks
        except SyntaxError:
            pass
    lines = text.splitlines()
    pattern = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?(?:function|class|const|let)\s+([\w$]+)")
    starts = [(i, m.group(1)) for i, line in enumerate(lines, 1) if (m := pattern.match(line))]
    if starts:
        return [CodeChunk(repository_id, rel, language, symbol, start,
                          (starts[i + 1][0] - 1 if i + 1 < len(starts) else len(lines)), "symbol", [],
                          "\n".join(lines[start - 1:(starts[i + 1][0] - 1 if i + 1 < len(starts) else len(lines))]))
                for i, (start, symbol) in enumerate(starts)]
    return [CodeChunk(repository_id, rel, language, Path(rel).stem, 1, len(lines), "module", [], text[:16000])]


code_index = CodeIndex()
