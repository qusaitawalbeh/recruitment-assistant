# AI Recruitment Screening Assistant

A recruitment assistant that helps HR screen CVs received through Gmail.
The system supports HR in making decisions; it does not make hiring decisions by itself.

> **Project status: Week 1, in progress.** Stages 1-6 are complete and tested.
> Stage 7 (AI extraction) has code written but is not yet validated. Stage 8 (matching) has not started.

## Progress

| # | Stage | Status |
|---|-------|--------|
| 1 | Project setup (venv, Git, .env) | Done |
| 2 | Gmail connection (OAuth 2.0, read-only) | Done |
| 3 | Understanding and processing Gmail messages | Done |
| 4 | Finding and downloading CV files (PDF / DOCX) | Done |
| 5 | Text extraction from CVs | Done |
| 6 | Job description preparation | Done |
| 7 | AI extraction with Ollama (`qwen3:8b`) | Code written, not yet tested |
| 8 | CV-to-job matching with embeddings | Not started |

## Pipeline implemented so far

```
Gmail -> search job-related emails -> download PDF/DOCX attachments -> extract text -> store candidate data
```

## Setup

1. Create and activate a virtual environment, then install dependencies:
```
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
```
2. Copy `.env.example` to `.env` and adjust values if needed.
3. Create a Google Cloud project, enable the Gmail API, and create an OAuth client
   (Desktop app). Download it as `credentials/credentials.json`.
   Only the `gmail.readonly` scope is requested.
4. Run `python main.py`. On first run a browser window opens for consent;
   the token is saved to `credentials/token.json` and reused afterwards.
5. For stage 7, install [Ollama](https://ollama.com) and run `ollama pull qwen3:8b`.

`credentials/`, `.env`, `token.json`, downloaded CVs, and candidate data are excluded
from Git because they contain secrets and personal data.

## How job-related emails are recognized

`main.py` builds a Gmail search query that requires:
- an attachment named `*.pdf` or `*.docx`
- a subject containing one of: application, CV, resume, job (also Arabic equivalents)
- a date within the last 30 days (configurable)

Keywords and the time window are set at the top of `main.py`.
Processed message IDs are saved so the same email is never processed twice, and an email
is marked as processed only after at least one CV was successfully read.

## Design decisions

- **Read-only Gmail access** so the app can never modify or delete mail.
- **Unsupported or unreadable files are reported, not guessed.** Blank, scanned, corrupted,
  or password-protected PDFs are rejected with a clear message instead of continuing with empty text.
- File type is checked by extension and by file signature (`%PDF` / `PK`).
- Multiple attachments in one email are handled individually.

## Known limitations

- PDFs with complex layouts (columns, separated headings) may produce text in an imperfect
  order with `pypdf`. `pymupdf` is a possible future improvement.
- Scanned PDFs have no extractable text (OCR is not implemented).
- Subject-based email detection can miss applications with unusual subjects.
- The same candidate applying twice is currently stored as two entries.

## Project structure

```
src/
  gmail_auth.py      OAuth authentication
  gmail_reader.py    search, parse, download attachments
  cv_extractor.py    PDF/DOCX text extraction
  job_loader.py      loads the job description
  storage.py         stores candidate data
  ai_extractor.py    Ollama extraction prompts (stage 7, in progress)
  matcher.py         matching (stage 8, not started)
data/job_description.txt   sample job description
main.py                    runs the Gmail -> CV text pipeline
test_extract.py            manual test for text extraction
```

## Next steps

- Validate and tune the extraction prompts (stage 7).
- Implement requirement matching with evidence and embeddings (stage 8).