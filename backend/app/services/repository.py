import fnmatch
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from app.config import get_settings

IGNORE_NAMES = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build",
    "coverage", ".pytest_cache", ".mypy_cache", ".next", "target", "vendor",
}
SECRET_PATTERNS = (".env", "*.pem", "*.key", "id_rsa*", "credentials.json")
EXTENSIONS = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".java": "Java",
    ".go": "Go", ".cpp": "C++", ".cc": "C++", ".h": "C++",
}


class RepositoryError(ValueError):
    pass


def _safe_files(root: Path):
    settings = get_settings()
    root = root.resolve()
    total = 0
    for path in root.rglob("*"):
        if not path.is_file() or any(part in IGNORE_NAMES for part in path.parts):
            continue
        rel = path.relative_to(root).as_posix()
        if any(fnmatch.fnmatch(path.name, pat) for pat in SECRET_PATTERNS):
            continue
        size = path.stat().st_size
        total += size
        if total > settings.max_repository_size_mb * 1024 * 1024:
            raise RepositoryError("Repository exceeds configured size limit")
        if size <= settings.max_file_size_kb * 1024:
            yield path, rel, size


def prepare_repository(source: str, repository_id: int) -> Path:
    settings = get_settings()
    workspace = settings.workspace_root.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    target = (workspace / str(repository_id)).resolve()
    if workspace not in target.parents:
        raise RepositoryError("Unsafe workspace path")
    parsed = urlparse(source)
    if source.lower().startswith(("http://", "https://")):
        if parsed.scheme != "https" or parsed.hostname not in {"github.com", "www.github.com"}:
            raise RepositoryError("Only public HTTPS GitHub URLs are supported")
        if not re.fullmatch(r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?/?", parsed.path):
            raise RepositoryError("Invalid GitHub repository URL")
        result = subprocess.run(
            ["git", "clone", "--depth", "1", source, str(target)],
            capture_output=True, text=True, timeout=120, check=False,
        )
        if result.returncode:
            raise RepositoryError(f"Clone failed: {result.stderr.strip()[-500:]}")
        return target
    local = Path(source).expanduser().resolve()
    if not local.is_dir():
        raise RepositoryError("Local repository path does not exist")
    target.mkdir(parents=True, exist_ok=False)
    for path, relative, _ in _safe_files(local):
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
    return target


def _frameworks(root: Path, files: list[str]) -> list[str]:
    found: set[str] = set()
    dependency_text = ""
    for name in ("requirements.txt", "pyproject.toml", "package.json"):
        path = root / name
        if path.exists():
            dependency_text += path.read_text(encoding="utf-8", errors="ignore").lower()
    checks = {
        "FastAPI": "fastapi", "Django": "django", "Flask": "flask",
        "React": "react", "Next.js": "next", "Express": "express",
        "Vue": "vue", "NestJS": "@nestjs",
    }
    for framework, marker in checks.items():
        if marker in dependency_text:
            found.add(framework)
    return sorted(found)


def profile_repository(root: Path) -> tuple[dict, list[dict]]:
    languages: Counter[str] = Counter()
    source_files: list[str] = []
    test_files: list[str] = []
    config_files: list[str] = []
    entries: list[str] = []
    file_records: list[dict] = []
    total_bytes = 0
    config_names = {"pyproject.toml", "package.json", "tsconfig.json", "vite.config.ts",
                    "docker-compose.yml", "Dockerfile", "requirements.txt"}
    for path, rel, size in _safe_files(root):
        total_bytes += size
        language = EXTENSIONS.get(path.suffix.lower())
        if language:
            languages[language] += 1
            source_files.append(rel)
        if "test" in path.stem.lower() or any(p in {"tests", "__tests__"} for p in path.parts):
            test_files.append(rel)
        if path.name in config_names or path.suffix in {".yaml", ".yml", ".toml"}:
            config_files.append(rel)
        if path.name in {"main.py", "app.py", "index.js", "index.ts", "server.js", "server.ts"}:
            entries.append(rel)
        file_records.append({"path": rel, "size": size, "language": language})
    package_manager = "unknown"
    for marker, manager in (("uv.lock", "uv"), ("poetry.lock", "poetry"), ("pyproject.toml", "pip"),
                            ("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"), ("package.json", "npm")):
        if (root / marker).exists():
            package_manager = manager
            break
    readme = next((p for p in root.iterdir() if p.is_file() and p.name.lower().startswith("readme")), None)
    profile = {
        "project_name": root.name,
        "languages": [{"name": name, "files": count} for name, count in languages.most_common()],
        "frameworks": _frameworks(root, source_files),
        "package_manager": package_manager,
        "entry_points": sorted(entries)[:20],
        "important_directories": sorted({Path(f).parts[0] for f in source_files if len(Path(f).parts) > 1})[:30],
        "source_files": len(source_files), "test_files": len(set(test_files)),
        "configuration_files": sorted(config_files)[:50],
        "readme_excerpt": readme.read_text(encoding="utf-8", errors="ignore")[:1200] if readme else "",
        "statistics": {"files": len(file_records), "bytes": total_bytes, "lines": _line_count(root, file_records)},
    }
    return profile, file_records


def _line_count(root: Path, records: list[dict]) -> int:
    total = 0
    for record in records:
        if record["language"]:
            try:
                total += len((root / record["path"]).read_text(encoding="utf-8", errors="ignore").splitlines())
            except OSError:
                pass
    return total


def repository_tree(root: Path) -> list[dict]:
    return [record for record in profile_repository(root)[1]]
