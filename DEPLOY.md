# Choosing Allah PDF API: deployment and alignment

This repository is the print service used by the Lovable website. It is not the website itself. Keep the existing Render Docker service and the supplied Georgia fonts.

## Apply the paired update

1. Merge the four changed frontend files into the CURRENT Lovable project, preserving all later edits. Do not replace the whole project or restore an old ZIP. Until the API update is deployed, exports show an explicit upgrade message instead of sending a chapter request to an old whole-book endpoint.
2. Merge the API changes into this repository and redeploy its existing Docker service. The existing Dockerfile installs the updated requirements, including qrcode. No additional email service, QR service, database migration or project files are needed.
3. Keep CHAPTERS_API_TOKEN set to the SAME existing secret in both the Lovable server environment and Render. Do not put it in a VITE_ variable, frontend code, URL or chat message.
4. After deployment, /health reports api_version: 2 and status: "ok". All manuscript/PDF endpoints require X-API-Token, including reads.
5. Re-export PDFs that need the clickable QR. Existing downloaded PDFs and published reader releases are NOT rewritten. Preparing a reader release remains private until the author explicitly publishes it.

Avoid exports while these two deployments are being applied. No application data, manuscript prose, live comments, reader approvals or email settings should be replaced as part of this update.

## What the source audit found

| Area | Before | Updated behaviour |
| --- | --- | --- |
| Manuscript and chapter order | All 26 shared Markdown files and both bundled manifests already match the supplied frontend. | Left untouched. The live editor revisions are sent as a fixed build snapshot, including the preface and front matter. |
| Chapter export | The frontend temporarily replaced the live manifest and cleared the cover, then ran a whole-book build. | Explicit chapter mode prints only the selected section; no temporary live manifest or cover changes. |
| Prelude export | Before we begin and front matter are not entries in the chapter manifest. | Both are supported directly. Front matter exports its copyright, epigraph and dedication pages. |
| Contents export | A JSON editor file was treated like a chapter. | The API paginates the selected full book, then returns only the Contents pages with the matching printed page numbers. |
| Reader releases | A second renderer used a different trim size and design. | Uses this same 5.5 × 8.5-inch print service with the exact fixed Markdown sent to the web reading view. |
| QR and navigation | The QR image had no link; the finishing pass also discarded all PDF links. | Locally generated QR and clickable image both open https://choosingallah.com/resources. Links survive mirrored margins; Contents links and PDF bookmarks are included. |
| References | 46 of 57 mapped citation locations used numbers from the older reference list. | Corrected against the provided frontend. Each mapping also has a source identity; live reference numbers are resolved from the website's current reference entries. |
| Privacy | Manuscript reads and the last PDF were public; missing configuration left writes open. | All manuscript reads, writes and downloads require the shared server token; missing configuration fails closed. |
| Storage and response files | Direct writes could be partial; builds shared output files. | Atomic saves, private build folders, unique streamed downloads, timeout cleanup. A chapter export never replaces the last full-book PDF. |
| Local scripts | Near-duplicate scripts included old absolute paths. | Existing local entry points delegate to the same server implementation. |

The reference work aligns existing mappings; it does not verify the book's factual claims or invent citations for all 102 website references. If an existing mapped source becomes missing or ambiguous in the live list, export stops with a specific source name instead of silently citing a different work. A passage edited so it no longer contains a mapping's search phrase still needs its citation placement reviewed.

The finishing pass explicitly restores annotations because [PyMuPDF's page-copy operation does not copy links](https://pymupdf.readthedocs.io/en/latest/page.html#Page.show_pdf_page). QR generation uses the existing deployment's Python requirements and the [qrcode SVG factory](https://pypi.org/project/qrcode/8.2/); it no longer calls a third-party QR endpoint.

## Server configuration

| Variable | Where | Purpose |
| --- | --- | --- |
| CHAPTERS_API_TOKEN | Render and Lovable server | Required, matching secret. Never browser-visible. |
| CHAPTERS_API_URL | Lovable server only | Optional. Defaults to https://choosing-allah-api.onrender.com. |
| CHAPTERS_DATA_DIR | Render only | Optional dedicated directory on an already configured persistent disk. Stores src16 and the last full-book PDF. |
| CHAPTERS_ALLOWED_ORIGINS | Render only | Optional comma-separated explicit origins for a separately authorised browser client. Normal Lovable server-to-server calls do not need CORS. |
| CHROMIUM_PATH | Render only | Optional custom Chromium executable; otherwise the existing Playwright install is used. |

Keep one Uvicorn worker, as in the existing Dockerfile. The service bounds a build to five minutes and rejects overlapping builds with a retryable busy message. It does not run a publication job or notify readers.

Without a persistent disk, Render's working files can reset on redeploy. The frontend now requires a durable revision before updating the print-service copy, and export sends its own current source snapshot. Do not replace chapter_revisions or other Supabase data with bundled Markdown.

When CHAPTERS_DATA_DIR is enabled, initial repository files seed only missing disk files. A redeploy does not overwrite existing disk edits. Deliberate GitHub manuscript changes then need to be reconciled through the editor, not copied over a live manuscript automatically.

## API contract

All routes below except /health require the X-API-Token header. Responses containing manuscript data use private, no-store caching and must not be proxied as public content.

| Method | Route | Result |
| --- | --- | --- |
| GET | /health | Public liveness/configuration state and API version. |
| GET | /chapters | Private manuscript inventory and content. |
| GET | /chapter/{filename} | One manuscript/configuration file. |
| PUT | /chapter/{filename} | Atomically save JSON body {"content": "..."}. Supports valid new Markdown filenames. |
| POST | /build | Build a private snapshot and return the PDF directly. |
| GET | /pdf | Private download of the most recent successful full-book PDF. |

Example chapter build body:

~~~json
{
  "mode": "chapter",
  "filename": "f_01.md",
  "title": "1. Who is Allah?",
  "manifest": [
    {"file": "f_01.md", "title": "1. Who is Allah?", "anchor": "a-1"}
  ],
  "sources": {"f_01.md": "The exact saved or prepared-release Markdown."},
  "cover_url": "",
  "references": []
}
~~~

The website sends its actual manifest, source text and current reference list, not this illustrative text. Whole-book requests use mode "book", omit filename, and include the selected chapters plus f_00_front_matter.md and f_00_preface_clean.md. includeInFinal: false is honoured. Explicit single-chapter exports may still export a chapter excluded from the final book.

filename "manifest.json" requests a Contents-only PDF, with full-book sources and the current cover URL so page numbers match that same book. The Contents-only PDF deliberately omits links to chapter pages absent from the extracted document.

Successful build responses contain X-Build-Contract: 2, X-Build-Mode and X-Pages. The frontend checks the API version before posting and verifies the response contract and PDF signature before downloading. Do not restore the previous manifest-swapping fallback.

For compatibility, a body-less POST /build still uses the service's stored manuscript. It does not fetch Lovable revisions or live reference entries by itself. Use the updated frontend for exports aligned with the editor and website.

## Applying this without undoing newer Lovable changes

The frontend patch touches only:

- src/lib/chapters.functions.ts: private API calls, fixed build payloads, durable saves and capability checks.
- src/lib/chapters.ts: optional exact-text snapshot for chapter exports.
- src/components/editor/recent-changes.tsx: use the print service when preparing a reader release; keep publish: false and makeCurrent: false.
- src/routes/admin.tsx: preview the current editor text, reflect newly saved API chapters, and show useful save errors.

Treat the supplied frontend diff as the change specification and merge it into the latest files. Keep all newer page copy, routing, mobile fixes, live margin notes, admin controls and release/publishing decisions. Do not add unrelated redesigns, offline/Safari/visual QA work, emails, migrations or new project files.
