"""Choosing Allah PDF Build API"""
import json, os, subprocess, threading
from pathlib import Path
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Choosing Allah Editor API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE = Path(__file__).parent
SRC  = BASE / "src16"
PDF  = BASE / "interior.pdf"
MANIFEST = SRC / "manifest.json"

# Write access is guarded by a shared secret when CHAPTERS_API_TOKEN is set
# in the environment. The Lovable server functions already send it as the
# X-API-Token header. Without the env var, behavior is unchanged (open).
API_TOKEN = os.environ.get("CHAPTERS_API_TOKEN", "")


def _check_token(x_api_token: str | None):
    if API_TOKEN and x_api_token != API_TOKEN:
        raise HTTPException(401, "Invalid or missing X-API-Token")


def _safe_path(filename: str) -> Path:
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "Invalid filename")
    return SRC / filename

_build_lock = threading.Lock()

# These files sit outside the printed manifest but are still editable. Printed
# chapter titles and order are loaded from manifest.json so the API cannot drift
# away from the editor's canonical spine again.
STATIC_CHAPTER_NAMES = {
    "f_00_front_matter.md":  "Dedication, Epigraph & Copyright",
    "f_00_preface_clean.md": "Before we begin (Preface)",
    "manifest.json":         "Contents (chapter titles and order)",
    "glossary.md":           "Glossary (term definitions, not printed)",
}

PRELUDE_FILES = ("f_00_front_matter.md", "f_00_preface_clean.md")
EDITOR_FILES = ("manifest.json", "glossary.md")


def _manifest_entries() -> list[dict]:
    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [entry for entry in data if isinstance(entry, dict)]


def _chapter_names() -> dict[str, str]:
    names = dict(STATIC_CHAPTER_NAMES)
    for entry in _manifest_entries():
        filename = entry.get("file")
        title = entry.get("title")
        if isinstance(filename, str) and isinstance(title, str):
            names[filename] = title
    return names


def _chapter_order() -> list[str]:
    ordered = list(PRELUDE_FILES)
    ordered.extend(
        entry["file"]
        for entry in _manifest_entries()
        if isinstance(entry.get("file"), str)
    )
    ordered.extend(EDITOR_FILES)
    # Keep the first occurrence when a special editor file also appears in the
    # manifest, as References currently does.
    return list(dict.fromkeys(ordered))


class ChapterBody(BaseModel):
    content: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/chapters")
def list_chapters():
    out = []
    names = _chapter_names()
    for fname in _chapter_order():
        path = SRC / fname
        if path.exists():
            out.append({
                "file": fname,
                "name": names.get(fname, fname),
                "content": path.read_text(encoding="utf-8")
            })
    return out


@app.get("/chapter/{filename}")
def get_chapter(filename: str):
    path = _safe_path(filename)
    if not path.exists():
        if filename == "f_cover_url.md":
            content = ""
        else:
            raise HTTPException(404, f"{filename} not found")
    else:
        content = path.read_text(encoding="utf-8")
    return {
        "file": filename,
        "name": _chapter_names().get(filename, filename),
        "content": content
    }


@app.put("/chapter/{filename}")
def update_chapter(filename: str, body: ChapterBody, x_api_token: str | None = Header(default=None)):
    _check_token(x_api_token)
    path = _safe_path(filename)
    existed = path.exists()
    can_create = (
        filename in {"f_cover_url.md", "manifest.backup.json"}
        or (
            filename.endswith(".md")
            and len(filename) <= 120
            and filename[0].isalnum()
            and all(char.isalnum() or char in "._-" for char in filename)
        )
    )
    if not existed and not can_create:
        raise HTTPException(400, f"{filename} cannot be created")
    path.write_text(body.content, encoding="utf-8")
    return {"ok": True, "file": filename, "created": not existed}


@app.post("/build")
def build_pdf(x_api_token: str | None = Header(default=None)):
    _check_token(x_api_token)
    if not _build_lock.acquire(blocking=False):
        raise HTTPException(503, "A build is already in progress. Try again in a moment.")
    try:
        cmd = " && ".join([
            f'cd "{BASE}"',
            "python3 build_v11_server.py",
            "node render.js pass1.pdf",
            "python3 find_pages_v11_server.py",
            "python3 build_v11_server.py page_map_v11.json",
            "node render.js interior_v11_raw.pdf",
            "python3 stamp_v11_server.py interior_v11_raw.pdf",
        ])
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            # Include the stdout tail too: the build scripts print the page
            # map and totals there, which is what you need to diagnose
            # anchor/pagination failures.
            err = (r.stderr or "").strip()[-2000:]
            log = (r.stdout or "").strip()[-1000:]
            raise HTTPException(500, f"Build failed:\n{err}\n--- build log tail ---\n{log}")
        if not PDF.exists():
            raise HTTPException(500, "Build succeeded but PDF not found")
        return FileResponse(
            str(PDF),
            media_type="application/pdf",
            filename="interior.pdf",
            headers={"X-Pages": _page_count()}
        )
    finally:
        _build_lock.release()


@app.get("/pdf")
def download_pdf():
    if not PDF.exists():
        raise HTTPException(404, "No PDF yet. POST /build first.")
    return FileResponse(str(PDF), media_type="application/pdf", filename="interior.pdf")


def _page_count() -> str:
    try:
        import fitz
        return str(len(fitz.open(str(PDF))))
    except Exception:
        return "unknown"
