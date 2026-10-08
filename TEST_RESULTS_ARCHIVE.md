# Validation of Report Ready 2

Checked on 24 September 2026 in Linux with Python 3.12. This records completed checks, not a guarantee for every Word document.

| Check | Result |
| --- | --- |
| Backend regression suite | 25 tests passed |
| React component interaction suite | 4 tests passed |
| TypeScript and Vite production build | Passed |
| Running HTTP server smoke test | Health, built interface, upload, audit, format and download passed |
| Farming report regression | Content checks passed; rendered output remained 50 pages |

The backend suite covers table and caption alignment, nested and merged tables, preserved table-header contrast, lists and hanging indents, hyperlinks, native equations, fields and explicit page breaks, image fitting in multiple sections and columns, repeated header/footer formatting, existing page fields, disabled table cleanup, template learning, corrupt/oversized uploads, archive traversal, invalid settings, missing IDs, deletion of generated outputs and refusal to overwrite the source.

The interface suite checks recovery from server upload errors and network failures, invalidation of a previous download after settings change, and learning a reference without replacing the user's active report. These are simulated DOM interaction tests, not a live browser run.

## Farming report

The deliberately misaligned farming report was formatted using settings learned from the aligned reference. The output retained:

- 571 main-document paragraphs and 886 paragraphs including table cells.
- 9,954 words, including table text.
- 35 tables and 315 table-cell paragraphs.
- 14 picture placements containing 10 distinct embedded images.
- All body text, field tokens, hyperlinks, list properties, native equations and embedded assets checked by the formatter.

The update formatted 101 heading paragraphs, 14 captions, all 315 table paragraphs and all 14 standalone picture paragraphs. The document rendered to 50 pages in LibreOffice. All pages were reviewed in contact sheets, with selected pages inspected at larger size for alignment and layout. This sample did not reveal clipping or missing pictures. Word may paginate differently.

Formatting this sample took about 2.3 seconds in the test environment, excluding rendering. This is a single observation, not a cross-device performance guarantee.

## Checks still needed on Windows

- Double-click startup and automatic browser opening on the user's laptop. The launcher code was reviewed, but Windows batch execution was unavailable here.
- Microsoft Word PDF export and any installed Word dialogs or add-ins.
- Optional PDF-to-DOCX conversion with the extra converter dependency. PDF upload validation and rejection of direct PDF formatting were tested; conversion itself was not run.
- Live browser layout and interaction. The available browser could not connect to the local app, so the component tests and production build were used instead.

The test runner also reported an upstream deprecation notice about the HTTP test client; all backend tests passed. Production document formatting does not use that test client.
