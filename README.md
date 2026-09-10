# BOM Drawing Extractor V2

Accuracy-first local web app for extracting BOMs from engineering drawings.

## V2 features
- Multiple PDF/image drawings in one batch
- Multi-page PDFs
- Text/vector PDF + scanned/image PDF
- High-resolution OCR
- Drawing metadata: Area, Line No., Drawing No., Revision, Sheet No.
- Section-aware BOM extraction: fabrication / erection / cut pipe
- Engineering validation and review flags
- Consolidated Excel export
- Keeps Drawing + Revision + Sheet traceability for every row
- Exact 15-column BOM structure matching the supplied template

## Run on Windows
1. Install Python 3.11+.
2. Install Tesseract OCR and make sure `tesseract.exe` is on PATH.
3. Open terminal in this folder.
4. `py -m venv .venv`
5. `.venv\\Scripts\\activate`
6. `pip install -r requirements.txt`
7. `uvicorn app.main:app --reload`
8. Open `http://127.0.0.1:8000`

## Output workbook
- FINAL BOM
- FABRICATION BOM
- ERECTION BOM
- CUT PIPE
- REVIEW REQUIRED
- VALIDATION REPORT
- SOURCE OCR

## Accuracy note
This V2 has a strong local OCR/rules baseline. For production billing/procurement, add a vision-AI provider as a second extraction pass and compare AI vs OCR before final approval. The app intentionally flags uncertain fields instead of silently inventing them.
