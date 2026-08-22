"""Choosing Allah PDF Build API"""
import os, subprocess, threading
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

CHAPTER_NAMES = {
    "f_00_front_matter.md":  "Dedication, Epigraph & Copyright",
    "f_00_preface_clean.md": "Before we begin (Preface)",
    "f_00_intro.md":         "Introduction",
    "f_01.md": "1 · So, who is Allah?",
    "f_02.md": "2 · Why should you believe in Allah?",
    "f_03.md": "3 · Why the Qur'an is the word of Allah",
    "f_04.md": "4 · The man who carried the message",
    "f_05.md": "5 · Why Islam, and not another religion?",
    "f_06.md": "6 · La ilaha illallah",
    "f_07.md": "7 · The religion that reached you",
    "f_08.md": "8 · What is your purpose in life?",
    "f_09.md": "9 · Would the Maker leave you alone?",
    "f_10.md": "10 · Being Muslim in your own skin",
    "f_11.md": "11 · Isn't Islam unfair to women?",
    "f_12.md": "12 · Why does Allah let bad things happen?",
    "f_13.md": "13 · What happens after you die?",
    "f_14.md": "14 · How to return to Him",
    "f_15.md": "15 · How to properly seek knowledge",
    "f_16.md": "16 · How to believe what you already know",
    "f_17_final_word.md":    "Your turn",
    "manifest.json":         "Contents (chapter titles and order)",
    "f_18_references.md":    "References (online list, not printed)",
    "glossary.md":           "Glossary (term definitions, not printed)",
}

ORDER = list(CHAPTER_NAMES.keys())


class ChapterBody(BaseModel):
    content: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/chapters")
def list_chapters():
    out = []
    for fname in ORDER:
        path = SRC / fname
        if path.exists():
            out.append({
                "file": fname,
                "name": CHAPTER_NAMES.get(fname, fname),
                "content": path.read_text(encoding="utf-8")
            })
    return out


@app.get("/chapter/{filename}")
def get_chapter(filename: str):
    path = _safe_path(filename)
    if not path.exists() and filename != "f_cover_url.md":
        raise HTTPException(404, f"{filename} not found")
    return {
        "file": filename,
        "name": CHAPTER_NAMES.get(filename, filename),
        "content": path.read_text(encoding="utf-8")
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
    if not existed and filename.endswith(".md") and filename != "f_cover_url.md":
        ORDER.append(filename)
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
