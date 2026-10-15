# AI Recruitment Screening Assistant

A local recruitment assistant that collects PDF/DOCX CVs from Gmail or uploads,
extracts candidate information with Ollama, and compares each CV against HR-reviewed
job requirements. HR selects Must-Haves and makes every Shortlist, Review Later or
Reject decision. Screening never automatically rejects candidates.

## Week 2 workflow

Create job → Ollama extracts requirements → HR edits and confirms Must-Haves →
collect CVs → extract text and structured candidate data → assess each requirement
with quoted evidence and semantic context → separate Must-Have gaps → rank qualified
candidates → HR reviews the original CV and records a decision.

Implemented: validated AI extraction, matching, batch processing, SQLite persistence,
per-job duplicate detection, configurable Top N, FastAPI, three Streamlit pages,
manual decisions, re-screening and automated tests. Live Gmail/Ollama integration
requires the local services and credentials described below.

## Installation

Python 3.11 or 3.12 is recommended. From the repository directory, on Windows:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-semantic.txt
Copy-Item .env.example .env
ollama pull qwen3:8b
```

Install [Ollama](https://ollama.com) first and ensure its server is running
(`ollama serve` if necessary). The first semantic screening downloads
`sentence-transformers/all-MiniLM-L6-v2` from Hugging Face; subsequent runs use
the local cache. This model compares normalized embeddings using cosine similarity.

For a lighter setup, install `requirements.txt` and set `ENABLE_EMBEDDINGS=false`
in `.env`. Ollama remains required; semantic evidence is clearly marked disabled
in the results. No fabricated/demo model output is used in the application.

Configuration in `.env`:

| Variable | Default / purpose |
| --- | --- |
| `OLLAMA_MODEL` | `qwen3:8b` |
| `OLLAMA_HOST` | `http://localhost:11434` |
| `OLLAMA_TIMEOUT` | `180` seconds per model request |
| `OLLAMA_CONTEXT` | `16384` tokens; oversized prompts fail explicitly instead of risking truncation |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` |
| `ENABLE_EMBEDDINGS` | `true` |
| `API_URL` | `http://127.0.0.1:8000` |
| `DATA_DIR` | Absolute repository `data/` directory; optional override |
| `GMAIL_CREDENTIALS_PATH` | `credentials/credentials.json` |
| `GMAIL_TOKEN_PATH` | `credentials/token.json` |

Run from the repository directory so relative OAuth paths resolve correctly.

## Start the application

In one terminal:

```powershell
python -m uvicorn src.api:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal with the same virtual environment:

```powershell
python -m streamlit run app.py --server.address 127.0.0.1
```

Open [the interface](http://127.0.0.1:8501) and
[interactive API documentation](http://127.0.0.1:8000/docs).

1. **Jobs & requirements:** enter a title and description. Review AI output, edit
   rows, and check Must-Have criteria. All criteria start unchecked so HR explicitly
   decides what is mandatory. Confirm before screening. Criteria not marked Must-Have
   contribute equally to the preferred score. Added rows need unique IDs.
2. **Screening:** upload multiple PDF/DOCX CVs or enter a job-specific Gmail query.
   Each file reports processed, duplicate or error. One bad file does not stop the batch.
3. **Results & HR review:** see totals, configurable Top N, all qualified candidates
   and candidates with Must-Have gaps. Inspect each match, quote, missing criterion,
   extracted information and original CV. Record an HR decision.
4. Editing requirements invalidates previous rankings. **Re-screen saved CVs** to
   update them; existing HR decisions remain unchanged. Re-uploading a duplicate
   does not re-screen it.

## Gmail configuration

1. Create a Google Cloud project and enable Gmail API.
2. Configure the OAuth consent screen (add your Gmail account as a test user when
   the app is in testing mode). Create a Desktop app OAuth client.
3. Save the downloaded credentials to `credentials/credentials.json`.
4. Use **Collect & screen Gmail CVs**. The first request opens the OAuth consent
   browser. Only `https://www.googleapis.com/auth/gmail.readonly` is requested.
   The saved token is reused and refreshed when possible.

Example query: `subject:"Junior Data Scientist" newer_than:30d`, or use a dedicated
label such as `label:applications-data-scientist`. The system adds PDF/DOCX attachment
filters. HR is responsible for associating the correct query with the selected job.
No emails are sent, modified, marked read, or deleted. Successful messages and
individual attachments are recorded per job in SQLite. Repeated collection skips
completed messages before fetching their contents, and skips successful attachments
before downloading them when a sibling attachment failed. Failed files remain
retryable. Content hashes also prevent duplicates across different emails.

The Week 1 JSON candidate/processed-ID files are preserved but not automatically
imported: old entries have no job association. Re-run the job-specific Gmail query
or upload those original CVs to create Week 2 records.

## Matching and ranking

- Ollama returns a validated assessment for every requirement: `meets`,
  `partially_meets`, `does_not_meet`, or `no_evidence`.
- Every usable assessment must contain a quote found in the CV (case and whitespace
  normalized). Invented or absent quotations become `no_evidence`.
- Alternative qualifications joined by OR stay together as one criterion. A degree
  in Computer Science OR Data Science requires one acceptable degree, not both,
  and contributes only once to the score.
- Numeric minimum experience checks guard against a quoted duration below the
  requirement. Quotes with multiple durations, unrelated experience, negations,
  ranges or no explicit duration are downgraded for HR review. A short quote tying
  one duration to the requested experience can pass; unrelated durations are never
  selected by taking the maximum. Date arithmetic is deliberately not assumed.
- Embeddings identify related passages, supplied to the assessment model as context.
  Cosine similarity is displayed but never used alone to pass a Must-Have.
  Complete cached embedding models load locally without Hub metadata requests.
  Assessments run in small batches to keep larger requirement lists within context.
- A candidate qualifies only when **every** Must-Have is `meets`. Partial, absent,
  and unmet Must-Haves remain accessible in the review group.
- Qualified candidates rank by preferred score: full match = 1, partial = 0.5,
  unmet/no evidence = 0, divided by the number of preferred criteria × 100.
  With no preferred criteria, scores are 0 and candidates tie. Ties use application
  creation time, then ID, for stable ordering. The score is not a hiring probability.
- HR decisions are stored separately from qualification and score.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Server health (not dependency readiness) |
| POST / GET | `/jobs` | Create a job with AI extraction / list jobs |
| GET | `/jobs/{id}` | Job details |
| PUT | `/jobs/{id}/requirements` | Edit criteria and confirm Must-Haves |
| POST | `/jobs/{id}/screen/uploads` | Multipart `files` batch |
| POST | `/jobs/{id}/screen/gmail` | JSON `query`, `max_results` |
| POST | `/jobs/{id}/rescreen` | Re-evaluate stored applications |
| GET | `/jobs/{id}/candidates?top_n=20` | Statistics, ranked/review groups |
| GET | `/candidates/{id}` | Evidence and candidate information |
| GET | `/candidates/{id}/cv` | Original document download |
| PATCH | `/candidates/{id}/decision` | JSON `decision`: `shortlist`, `review_later`, `reject` |

Validation errors return 422; missing resources 404; job extraction or Gmail
dependency failures 503. File-level failures are reported in the batch's `results`
under a 200 response, so always inspect every item's `status` and `error`.
Screening requests are synchronous and may take minutes on a CPU.
All JSON endpoints declare Pydantic response models as well as validated request
models. Private CV text, internal storage paths and file hashes are excluded from
candidate responses. `/docs` publishes the request and response schemas.

The CLI uses the same processing and persistence:

```powershell
python main.py --job-id JOB_ID --files "path\candidate.pdf" "path\candidate.docx"
python main.py --job-id JOB_ID --gmail-query 'subject:"Junior Data Scientist" newer_than:30d'
python main.py --job-id JOB_ID --rescreen
```

## Tests and live verification

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Automated tests use temporary databases and synthetic documents. Model responses,
embeddings and Gmail calls are replaced with controlled fixtures, so tests run
without credentials, downloads or mail access. They exercise the API workflow,
PDF/DOCX extraction, duplicate detection, independent errors, evidence validation,
Must-Have gating, ranking, decisions, persistence and stale-result handling.
They do not establish the quality of real Ollama assessments.

Run the opt-in live acceptance checks with real Ollama and the embedding model:

```powershell
python -m scripts.acceptance
```

To include one application already collected from your Gmail account:

```powershell
python -m scripts.acceptance --gmail
```

The Gmail option locates one known application using its RFC Message-ID and uses
read-only access. All acceptance jobs, generated CVs and results use a temporary
database; normal application data is preserved. It checks PDF/DOCX batches,
qualified and unqualified CVs, mixed experience durations, OR qualifications,
ranking, original-file retrieval, HR decisions, duplicates, two jobs, semantic
paraphrases and the Streamlit results page. The default report is
`tmp/live-acceptance.json` and contains check results, not private CV content.
GitHub Actions runs the offline suite on pushes and pull requests; live checks
remain opt-in because they need local models and, optionally, Gmail credentials.

For jobs created before the alternative-qualification fix:

```powershell
python -m src.maintenance repair-education
```

This explicitly backs up the database under ignored `data/backups/`, combines a
single source education criterion that was previously split into alternatives,
and increments the affected job revision. It preserves applications and HR
decisions. Re-screen affected saved CVs afterwards; older results are marked stale.

For live acceptance, create the sample job, confirm criteria, process several test
CVs through both upload and Gmail, rerun to verify duplicates, then inspect evidence
and record each HR decision. Test an unreadable file alongside a valid one and
change criteria before re-screening. Use examples with missing mandatory skills,
partial preferred skills and differently worded experience.

## Storage, limits and limitations

SQLite stores job/application data in `data/recruitment.sqlite3`; originals live in
`data/cvs/{job_id}/` under content-hash filenames. A unique `(job_id, file_hash)`
constraint prevents repeated identical applications within a job, including across
different emails. Different file bytes, even for the same person, are separate
applications. Files are limited to 10 MB and 60,000 extracted characters.
The combined prompt must also fit a conservative UTF-8 byte budget inside
`OLLAMA_CONTEXT`, reserving 4,096 tokens for instructions and output. Large CVs or
many criteria may need a larger context (within the installed model's limit).

Credentials, tokens, `.env`, databases, downloaded CVs and legacy candidate data
are ignored by Git. **This is a local single-user prototype without authentication.**
Keep both servers bound to localhost. Production use needs authentication, access
controls, encryption, retention/deletion policies and background workers.

Scanned CVs need OCR (not implemented). Complex PDF layouts can affect reading
order. LLMs can misinterpret valid quotations and requirements despite validation;
HR must review evidence. Explicit numeric duration guards are conservative and do
not calculate total years from dates. Semantic model downloads require internet
on first use. Gmail query selection does not infer the correct job automatically.

## Structure

```text
app.py                  Streamlit pages; talks to the backend with requests
main.py                 CLI for confirmed jobs
src/api.py              FastAPI endpoints
src/models.py           Pydantic contracts
src/database.py         SQLite storage
src/screening.py        Job mapping, uploads, Gmail and re-screening
src/requirements.py     Preserve alternative education criteria
src/maintenance.py      Backed-up repair of older saved jobs
src/ai_extractor.py      Schema-validated Ollama extraction and assessments
src/embeddings.py        Sentence Transformers / cosine similarity
src/matcher.py           Evidence guards, Must-Haves and ranking
src/cv_extractor.py      PDF/DOCX text extraction
src/gmail_auth.py        Read-only OAuth
src/gmail_reader.py      Gmail search, message parsing and attachments
src/storage.py          Legacy Week 1 JSON helpers
src/job_loader.py       Sample text loader
tests/                  Offline regression tests
scripts/acceptance.py    Opt-in real-service acceptance checks
docs/                   Sanitized acceptance results and verification notes
```
