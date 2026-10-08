# Report Ready 3.2 — Phase 3

Format a DOCX report with consistent body text, headings, tables, captions and inline images. Use a built-in template or learn common settings from a reference DOCX. The app creates a separate output file and keeps the original unchanged.

Billing, job quotas, team invitations and shared templates are implemented in this release. Payments remain disabled by default. Start with **PHASE3_SETUP.md** for account/Stripe sandbox setup and **PHASE_REVIEW.md** for the complete Phase 1–4 audit.

## Start on Windows

1. Extract the entire ZIP to a **new folder**. Do not run it from inside the ZIP.
2. Install Python 3.10 or newer if it is not already installed. Enable **Add Python to PATH** in the installer.
3. Double-click **start.bat**.
4. On first launch, wait while the app installs its Python packages. Internet access is needed for this setup step.
5. The app opens at **http://127.0.0.1:8000**. Keep the Report Ready window open while using it. Press Ctrl+C there to stop.

The ZIP includes the built interface, so **Node.js and a second terminal are not required for normal use**. Later launches reuse the isolated `.venv` environment. After setup, document formatting runs locally without an AI API key.

If the browser does not open, enter http://127.0.0.1:8000 yourself. If port 8000 is occupied, close the old Report Ready terminal and try again.

## Run as a multi-user web service

Report Ready 3 has accounts, a database and pluggable file storage. Copy the values from `.env.example` into your host's environment.

1. Set `REPORT_READY_SESSION_SECRET` (48+ random characters) and `REPORT_READY_COOKIE_SECURE=true`.
2. Point `DATABASE_URL` at Postgres. Tables are created and upgraded automatically on startup; run `cd backend && alembic upgrade head` yourself if you set `REPORT_READY_AUTO_MIGRATE=0`.
3. Choose file storage: `REPORT_READY_STORAGE=local` (a folder, single instance only) or `s3` with a bucket (AWS S3, Cloudflare R2 or MinIO).
4. Optional Google sign-in: create an OAuth client with redirect URI `<REPORT_READY_PUBLIC_URL>/api/auth/google/callback`, then set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` and `REPORT_READY_PUBLIC_URL`.

`render.yaml` provisions Postgres and the web service; add the bucket and credentials in the Render dashboard.

### Jobs, workers and PDF export

Formatting and PDF export are queued jobs. By default the web process runs two worker threads (`REPORT_READY_WORKERS`). To scale, set `REPORT_READY_WORKERS=0` on the web service and run `cd backend && python -m app.worker` as one or more separate services sharing the same database and storage.

PDF export needs LibreOffice on the machine running the workers (`soffice` on PATH, or set `REPORT_READY_SOFFICE`). The Dockerfile installs it with metric-compatible fonts. LibreOffice substitutes fonts it does not have, so line breaks can differ slightly from Word; the app says so next to the download.

To build and run the image locally: `docker build -t report-ready .` then `docker run -p 8000:8000 -e REPORT_READY_SESSION_SECRET=<48+ random characters> -e REPORT_READY_COOKIE_SECURE=false report-ready`.

Desktop use is unchanged: `start.bat` sets `REPORT_READY_LOCAL_MODE=1`, which skips accounts and stores data in `backend/data`.

After changing a model in `backend/app/db_models.py`, create a migration with `cd backend && alembic revision --autogenerate -m "describe change"`. The test suite fails if models and migrations drift apart.

## Format a report

1. Choose your DOCX or drop it onto the upload area.
2. Select a template. The generic template uses Times New Roman, 12 pt, justified body text and 1.5 line spacing.
3. Optionally open **Adjust format** to set fonts, heading sizes, margins, paper size and columns.
4. Open **Cleanup and finishing touches** to choose which kinds of cleanup to apply.
5. Click **Format my report**, then **Download DOCX**.
6. Open the copy in Word and check its page breaks, tables and complex objects before submission.

**Check formatting plan** is optional: it lists the content the app recognizes and identifies items needing manual review. The result screen is a change summary, not a visual Word page preview. Changing settings clears the previous result so you cannot accidentally download a copy made with different settings.

## Use a senior report as a reference

Upload your own report first. Click **Use a reference DOCX** and choose the senior report. The app saves and selects a template learned from observed body text, Heading 1–3 paragraphs and margins. Your own report remains selected.

Review the learned settings, then format your report. Reference learning transfers these common settings; it does not copy the reference's content, cover design, page breaks, tables, header wording or complete page layout. Use **Save as a new template** to retain adjustments.

## What is formatted

| Content | Behavior |
| --- | --- |
| Normal and Body Text paragraphs | Font, size, alignment, spacing and stray indentation |
| Word Heading 1–3 and derived heading styles | Font, size, alignment, spacing and keep-with-next |
| Title and Subtitle styles | Consistent title/subtitle formatting |
| Word lists | Text formatting while retaining numbering and hanging indents |
| Tables, including nested tables | Consistent text formatting and placement; oversized grids shrink proportionally; merged cells and table colors remain |
| Captions | Caption style and recognizable Figure/Table labels are centered with smaller text; short Illustration text directly after a picture is also recognized |
| Inline images | Center standalone images and shrink overflow to fit the section, column or table cell, without stretching |
| Headers and footers | Align existing text; optional additional text and missing PAGE fields; linked sections do not multiply additions |
| Page setup | Set margins; preserve dimensions and columns unless explicitly changed; preserve section orientation |

Cleanup options can be switched off when the source uses an intentional special layout. Blank header/footer inputs retain existing wording. Entered text is **added**, not used to erase existing header/footer content. Reformatting an app-generated copy updates the app's own added paragraph rather than appending it again.

## PDF options

- **PDF to DOCX:** run **enable-pdf.bat** once, then restart Report Ready. Conversion is an optional dependency to keep the normal installation lighter. It is intended for text-based PDFs. Scanned PDFs need OCR elsewhere first.
- **DOCX to PDF:** LibreOffice headless is the hosted/default export engine. On Windows, the optional desktop dependency also enables a Microsoft Word fallback. Install the chosen engine on the worker machine and review font substitutions and page breaks.
- PDF conversion can change layout, so review converted tables, equations and pictures carefully.

## Keep your existing work

Keep your original app folder as a backup. This package intentionally excludes uploaded documents, generated outputs, caches and installed dependencies from the previous app.

For a Phase 1/2 database installation, stop the app and back up the entire `backend/data` directory, then copy it into the new project folder. Keep the database and `files` directory together. Hosted deployments should retain their current database and bucket. Startup applies schema migrations. There is no automatic import of legacy `profiles.json` files; recreate those templates through the UI if you are upgrading from the older JSON-based app.

Use **Delete uploaded copy and outputs** to remove a report and its generated copies. Files otherwise expire according to the plan at creation. Closing a browser tab does not delete uploads. Do not delete stored files independently of the database. Account-wide erasure is still Phase 4 work.

## Continue development in VS Code

Open this entire extracted folder in VS Code. Source code is in `backend/app` and `frontend/src`.

For backend development:

```bat
.venv\Scripts\python -m pip install -r backend\requirements-dev.txt
cd backend
..\.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

For frontend development, use a Node version accepted by `frontend/package.json` (20.19+ in the 20 series, or 22.12+):

```bat
cd frontend
npm ci
npm run dev
```

The development interface runs on http://127.0.0.1:5173 and forwards API requests to port 8000. After changing the frontend, run **npm run build** so the normal launcher serves the updated interface.

Backend checks from `backend`:

```bat
..\.venv\Scripts\python -m pytest -q
```

Frontend checks from `frontend`:

```bat
npm test
npm run build
```

With the app running, a self-contained smoke test can be run from the project root:

```bat
.venv\Scripts\python create_test_report.py
.venv\Scripts\python run_test_pipeline.py
```

It creates a deliberately messy sample, uploads it, formats it, checks the returned counts and downloads the result into `test-assets`. You can also pass a DOCX path to `run_test_pipeline.py`.

## Limits and validation

Custom body styles, floating pictures, text boxes, unusual equations, tracked changes and complex layouts need manual review. The app keeps these objects in the document but does not claim to redesign them. A two-column template is a starter, not certification of IEEE or another publisher's requirements. Formatting can change page count.

The formatter compares body text and field tokens, paragraph/table structure, list properties, hyperlink targets, native equation XML and embedded asset hashes before accepting an output. This is stronger than checking word counts alone, but it does not replace visual review in Word.

See **TEST_RESULTS.md** for the checks completed on this update and the Windows-specific features that still need a laptop check.
