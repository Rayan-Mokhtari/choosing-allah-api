"""Private manuscript storage and request-scoped Choosing Allah PDF builds."""
import hashlib
import hmac
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.background import BackgroundTask

BASE = Path(__file__).resolve().parent
# Optional persistent disk. Existing files are never replaced by repo copies.
# Without a disk, the editor's revision store remains the durable source.
DATA = Path(os.environ.get("CHAPTERS_DATA_DIR", str(BASE))).resolve()
SRC = DATA / "src16"
PDF = DATA / "interior.pdf"
MANIFEST = SRC / "manifest.json"
API_TOKEN = os.environ.get("CHAPTERS_API_TOKEN", "")
MAX_CONTENT_BYTES = 2_000_000
MAX_SNAPSHOT_BYTES = 12_000_000
BUILD_TIMEOUT = 300
_source_lock = threading.RLock()
_build_lock = threading.Lock()

if DATA != BASE:
    SRC.mkdir(parents=True, exist_ok=True)
    for bundled in (BASE / "src16").iterdir():
        if bundled.is_file() and not (SRC / bundled.name).exists():
            shutil.copy2(bundled, SRC / bundled.name)

app = FastAPI(title="Choosing Allah Editor API", version="2.0", docs_url=None, redoc_url=None)
origins = [value.strip() for value in os.environ.get("CHAPTERS_ALLOWED_ORIGINS", "").split(",") if value.strip()]
if origins:
    app.add_middleware(
        CORSMiddleware, allow_origins=origins,
        allow_methods=["GET", "PUT", "POST"], allow_headers=["Content-Type", "X-API-Token"],
    )


@app.middleware("http")
async def private_responses(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


def _check_token(x_api_token: str | None):
    # A missing deployment secret must not make an unpublished book public.
    if not API_TOKEN:
        raise HTTPException(503, "CHAPTERS_API_TOKEN is not configured on the print service")
    if not x_api_token or not hmac.compare_digest(x_api_token.encode(), API_TOKEN.encode()):
        raise HTTPException(401, "Invalid or missing X-API-Token")


def _safe_filename(filename: str, markdown_only=False) -> str:
    if (
        not isinstance(filename, str) or len(filename) > 120 or ".." in filename
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", filename)
        or not (filename.endswith(".md") or (not markdown_only and filename in {"manifest.json", "manifest.backup.json"}))
    ):
        raise HTTPException(400, "Invalid manuscript filename")
    return filename


def _safe_path(filename: str) -> Path:
    path = SRC / _safe_filename(filename)
    if path.is_symlink():
        raise HTTPException(400, "Symlinks are not manuscript files")
    return path


def _validate_manifest(value) -> list[dict]:
    if not isinstance(value, list) or not value or len(value) > 500:
        raise HTTPException(400, "The manifest must be a non-empty chapter list")
    files, anchors = set(), set()
    for entry in value:
        if not isinstance(entry, dict):
            raise HTTPException(400, "Each manifest entry must be an object")
        filename, title, anchor = entry.get("file"), entry.get("title"), entry.get("anchor")
        if filename is not None:
            _safe_filename(filename, markdown_only=True)
            if filename == "f_cover_url.md" or filename in files:
                raise HTTPException(400, "The manifest contains a duplicate or non-chapter file")
            files.add(filename)
        if not isinstance(title, str) or not title.strip() or len(title) > 180:
            raise HTTPException(400, "Each chapter needs a title of at most 180 characters")
        if not isinstance(anchor, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,99}", anchor) or anchor in anchors:
            raise HTTPException(400, "Chapter anchors must be valid and unique")
        if anchor in {"a-preface", "a-toc", "a-front-matter"}:
            raise HTTPException(400, f"{anchor} is reserved for front matter")
        if "includeInFinal" in entry and not isinstance(entry["includeInFinal"], bool):
            raise HTTPException(400, "includeInFinal must be true or false")
        anchors.add(anchor)
    return value


def _manifest_entries() -> list[dict]:
    try:
        return _validate_manifest(json.loads(MANIFEST.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(500, "The stored manifest is unreadable; restore it from editor history") from exc


STATIC_CHAPTER_NAMES = {
    "f_00_front_matter.md": "Dedication, Epigraph & Copyright",
    "f_00_preface_clean.md": "Before we begin (Preface)",
    "manifest.json": "Contents (chapter titles and order)",
    "glossary.md": "Glossary (term definitions, not printed)",
}
PRELUDE_FILES = ("f_00_front_matter.md", "f_00_preface_clean.md")
EDITOR_FILES = ("manifest.json", "glossary.md")


def _chapter_names() -> dict[str, str]:
    names = dict(STATIC_CHAPTER_NAMES)
    names.update({entry["file"]: entry["title"] for entry in _manifest_entries() if entry.get("file")})
    return names


def _chapter_order() -> list[str]:
    ordered = [*PRELUDE_FILES]
    ordered.extend(entry["file"] for entry in _manifest_entries() if entry.get("file"))
    ordered.extend(EDITOR_FILES)
    # Keep auxiliary/recovery files readable. The frontend filters its sidebar;
    # only the manifest controls which chapters are printed.
    ordered.extend(path.name for path in sorted(SRC.glob("*.md")) if path.name != "f_cover_url.md")
    return list(dict.fromkeys(ordered))


def _atomic_write(path: Path, content: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".manuscript-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class ChapterBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(max_length=MAX_CONTENT_BYTES)


class ReferenceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    n: int = Field(gt=0, le=100000)
    md: str = Field(max_length=20000)


class BuildBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["book", "chapter"] = "book"
    filename: str | None = None
    title: str | None = Field(default=None, max_length=180)
    manifest: list[dict] | None = None
    sources: dict[str, str] = Field(default_factory=dict)
    cover_url: str | None = Field(default=None, max_length=8192)
    references: list[ReferenceBody] | None = Field(default=None, max_length=2000)


@app.get("/health")
def health():
    return {
        "status": "ok" if API_TOKEN else "configuration_required",
        "api_version": 2,
        "features": ["isolated-builds", "chapter-exports", "private-manuscripts", "clickable-links"],
    }


@app.get("/chapters")
def list_chapters(x_api_token: str | None = Header(default=None)):
    _check_token(x_api_token)
    with _source_lock:
        names = _chapter_names()
        return [
            {"file": filename, "name": names.get(filename, filename), "content": _safe_path(filename).read_text(encoding="utf-8")}
            for filename in _chapter_order() if _safe_path(filename).is_file()
        ]


@app.get("/chapter/{filename}")
def get_chapter(filename: str, x_api_token: str | None = Header(default=None)):
    _check_token(x_api_token)
    with _source_lock:
        path = _safe_path(filename)
        if not path.is_file() and filename != "f_cover_url.md":
            raise HTTPException(404, f"{filename} not found")
        content = path.read_text(encoding="utf-8") if path.is_file() else ""
        return {"file": filename, "name": _chapter_names().get(filename, filename), "content": content}


@app.put("/chapter/{filename}")
def update_chapter(filename: str, body: ChapterBody, x_api_token: str | None = Header(default=None)):
    _check_token(x_api_token)
    path = _safe_path(filename)
    content = body.content.encode("utf-8")
    if len(content) > MAX_CONTENT_BYTES:
        raise HTTPException(413, "This manuscript file is too large")
    if filename.endswith(".json"):
        try:
            _validate_manifest(json.loads(body.content))
        except json.JSONDecodeError as exc:
            raise HTTPException(400, "The manifest is not valid JSON") from exc
    with _source_lock:
        existed = path.exists()
        _atomic_write(path, content)
    return {"ok": True, "file": filename, "created": not existed, "sha256": hashlib.sha256(content).hexdigest()}


def _prepare_snapshot(job: Path, request: BuildBody):
    if request.mode == "chapter":
        if not request.filename or request.filename in {"f_cover_url.md", "manifest.backup.json"}:
            raise HTTPException(400, "Choose a chapter or front-matter file to export")
        _safe_filename(request.filename)
    elif request.filename is not None:
        raise HTTPException(400, "filename is only valid for a chapter export")
    if len(request.sources) > 500:
        raise HTTPException(413, "Too many manuscript files in this build")
    total = 0
    for filename, content in request.sources.items():
        _safe_filename(filename, markdown_only=True)
        if filename == "f_cover_url.md":
            raise HTTPException(400, "Use cover_url for the front cover")
        size = len(content.encode("utf-8"))
        total += size
        if size > MAX_CONTENT_BYTES or total > MAX_SNAPSHOT_BYTES:
            raise HTTPException(413, "The manuscript snapshot is too large")
    if request.references is not None:
        numbers = [reference.n for reference in request.references]
        if len(numbers) != len(set(numbers)):
            raise HTTPException(400, "Online reference numbers must be unique")
    with _source_lock:
        manifest = _validate_manifest(request.manifest) if request.manifest is not None else _manifest_entries()
        destination = job / "src16"
        destination.mkdir()
        for path in SRC.glob("*.md"):
            if path.is_file() and not path.is_symlink():
                shutil.copy2(path, destination / path.name)
        for filename, content in request.sources.items():
            (destination / filename).write_text(content, encoding="utf-8")
    (destination / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    if request.cover_url is not None:
        (destination / "f_cover_url.md").write_text(request.cover_url, encoding="utf-8")
    if request.references is not None:
        (job / "references.json").write_text(
            json.dumps([reference.model_dump() for reference in request.references], ensure_ascii=False), encoding="utf-8",
        )
    if request.mode == "chapter" and request.filename != "manifest.json":
        if not (destination / request.filename).is_file():
            raise HTTPException(404, f"No saved text for {request.filename}")
    else:
        chapters = [entry["file"] for entry in manifest
                    if entry.get("file") and entry.get("includeInFinal") is not False
                    and entry["anchor"] not in {"a-refs", "a-gloss"} and entry["file"] not in PRELUDE_FILES]
        if not chapters:
            raise HTTPException(400, "No chapters are selected for this book")
        missing = [filename for filename in (*PRELUDE_FILES, *chapters)
                   if not (destination / filename).is_file() or not (destination / filename).read_text(encoding="utf-8").strip()]
        if missing:
            raise HTTPException(400, "No saved text for: " + ", ".join(missing))


def _run(command: list[str], job: Path, env: dict[str, str], deadline: float):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise HTTPException(504, "The PDF build timed out; no manuscript files were changed")
    process = subprocess.Popen(
        command, cwd=job, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, start_new_session=True,
    )
    try:
        output, _ = process.communicate(timeout=remaining)
    except subprocess.TimeoutExpired as exc:
        # Kill Chromium as well as its parent before allowing another build.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate()
        raise HTTPException(504, "The PDF build timed out; no manuscript files were changed") from exc
    if process.returncode:
        raise HTTPException(500, f"PDF build failed during {Path(command[1]).name}:\n{output[-2500:]}")


def _render_snapshot(job: Path, request: BuildBody):
    env = {
        **os.environ, "BOOK_BUILD_DIR": str(job), "BOOK_ASSET_DIR": str(BASE),
        "BOOK_EXPORT_FILE": request.filename if request.mode == "chapter" else "",
        "BOOK_EXPORT_TITLE": request.title or "",
    }
    deadline = time.monotonic() + BUILD_TIMEOUT
    builder = [sys.executable, str(BASE / "build_v11_server.py")]
    finder = [sys.executable, str(BASE / "find_pages_v11_server.py")]
    renderer = ["node", str(BASE / "render.js")]
    _run(builder, job, env, deadline)
    _run([*renderer, "pass1.pdf"], job, env, deadline)
    _run([*finder, "pass1.pdf"], job, env, deadline)
    raw = "pass1.pdf"
    if request.mode == "book" or request.filename == "manifest.json":
        # Contents numbers can change wrapping. Check the final render's page
        # map and repeat only if necessary, rather than returning stale folios.
        for _ in range(3):
            before = json.loads((job / "page_map_v11.json").read_text())
            _run([*builder, "page_map_v11.json"], job, env, deadline)
            _run([*renderer, "interior_v11_raw.pdf"], job, env, deadline)
            _run([*finder, "interior_v11_raw.pdf"], job, env, deadline)
            raw = "interior_v11_raw.pdf"
            if before == json.loads((job / "page_map_v11.json").read_text()):
                break
        else:
            raise HTTPException(500, "Contents pagination did not settle; no PDF was returned")
    _run([sys.executable, str(BASE / "stamp_v11_server.py"), raw], job, env, deadline)


def _page_count(path: Path) -> str:
    import fitz
    with fitz.open(path) as document:
        if not len(document):
            raise HTTPException(500, "The typesetter produced an empty PDF")
        return str(len(document))


@app.post("/build")
def build_pdf(body: BuildBody | None = None, x_api_token: str | None = Header(default=None)):
    _check_token(x_api_token)
    request = body or BuildBody()
    if not _build_lock.acquire(blocking=False):
        raise HTTPException(503, "A PDF is already being prepared. Try again in a moment.", headers={"Retry-After": "5"})
    job = Path(tempfile.mkdtemp(prefix="choosing-allah-build-"))
    try:
        _prepare_snapshot(job, request)
        _render_snapshot(job, request)
        output = job / "interior.pdf"
        if not output.is_file():
            raise HTTPException(500, "The typesetter did not produce a PDF")
        pages = _page_count(output)
        # A chapter export never replaces the last full-book download.
        if request.mode == "book":
            with _source_lock:
                _atomic_write(PDF, output.read_bytes())
        filename = "interior.pdf" if request.mode == "book" else f"{Path(request.filename).stem}.pdf"
        return FileResponse(
            output, media_type="application/pdf", filename=filename,
            headers={"X-Pages": pages, "X-Build-Contract": "2", "X-Build-Mode": request.mode},
            # Each response owns its unique file until streaming has finished.
            background=BackgroundTask(shutil.rmtree, job, ignore_errors=True),
        )
    except BaseException:
        shutil.rmtree(job, ignore_errors=True)
        raise
    finally:
        _build_lock.release()


@app.get("/pdf")
def download_pdf(x_api_token: str | None = Header(default=None)):
    _check_token(x_api_token)
    job = Path(tempfile.mkdtemp(prefix="choosing-allah-download-"))
    try:
        with _source_lock:
            if not PDF.is_file():
                raise HTTPException(404, "No full-book PDF yet. Export the book first.")
            output = job / "interior.pdf"
            shutil.copy2(PDF, output)
        return FileResponse(
            output, media_type="application/pdf", filename="interior.pdf",
            background=BackgroundTask(shutil.rmtree, job, ignore_errors=True),
        )
    except BaseException:
        shutil.rmtree(job, ignore_errors=True)
        raise
