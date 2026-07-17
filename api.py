"""Choosing Allah — PDF Build API"""
import os, subprocess, threading
from pathlib import Path
from fastapi import FastAPI, HTTPException
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
    "f_19_refs_page.md":     "References page — printed text",
    "manifest.json":         "Contents — chapter titles & order",
    "f_18_references.md":    "References (online list — not printed)",
    "glossary.md":           "Glossary (term definitions — not printed)",
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
    path = SRC / filename
    if not path.exists():
        raise HTTPException(404, f"{filename} not found")
    return {
        "file": filename,
        "name": CHAPTER_NAMES.get(filename, filename),
        "content": path.read_text(encoding="utf-8")
    }


@app.put("/chapter/{filename}")
def update_chapter(filename: str, body: ChapterBody):
    path = SRC / filename
    if not path.exists():
        raise HTTPException(404, f"{filename} not found")
    path.write_text(body.content, encoding="utf-8")
    return {"ok": True, "file": filename}


@app.post("/build")
def build_pdf():
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
            raise HTTPException(500, f"Build failed:\n{r.stderr[-3000:]}")
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
        raise HTTPException(404, "No PDF yet — POST /build first")
    return FileResponse(str(PDF), media_type="application/pdf", filename="interior.pdf")


def _page_count() -> str:
    try:
        import fitz
        return str(len(fitz.open(str(PDF))))
    except Exception:
        return "unknown"
