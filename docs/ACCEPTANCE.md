# Acceptance and verification

Date: 2026-10-15 (Asia/Amman).

## Automated regression

Command: `python -m pytest -q`.

Current suite: **56 passed**, including API contracts, job creation and requirement review,
PDF/DOCX extraction, corrupt/blank/encrypted input, independent batch errors, verbatim
quote validation, OR education grouping, scoped/ambiguous duration guards, ranking,
HR decisions, original-CV retrieval, persistence, transaction rollback, backed-up
education repair, per-job hashes, completed-message skipping and partial Gmail retries.

The offline suite uses controlled model and mail outputs. It verifies application
logic and contracts; it does not measure unrestricted LLM accuracy.

## Real-service acceptance

Command: `python -m scripts.acceptance --gmail`.

Result: **8 live checks passed**. The sanitized machine-readable result is
[live-acceptance.json](live-acceptance.json).

1. Real Ollama job extraction and HR confirmation.
2. Real PDF/DOCX screening with an invalid file in the same batch.
3. Qualified candidate, missing mandatory skill, alternative degree and mixed Java/Python durations.
4. Ranking, original CV download, persisted HR decision and duplicate upload.
5. A second job description and per-job application identity.
6. Real embedding paraphrase: relational-database wording scored 0.5915 against SQL querying;
   unrelated watercolor wording scored 0.0852. These are observed scores, not universal thresholds.
7. Real read-only Gmail collection of one previously collected application, model screening,
   and repeat-collection skipping.
8. Actual Streamlit result page rendered against the processed data. HTTP transport was
   bridged to FastAPI TestClient; model and Gmail results were not mocked.

Acceptance jobs and documents use an isolated temporary database. Existing application
records, mailbox contents and HR decisions are not modified by this acceptance script.
The separate backed-up maintenance operation repairs previously split education criteria.

## Clean installation

A fresh `.venv` and local `.env` were created from README instructions.
Installation command: `python -m pip install -r requirements-dev.txt -r requirements-semantic.txt`.
Fresh-environment verification: **56 passed, 1 warning**; `python -m pip check`
reported **No broken requirements found**. Real Ollama extraction and real cached
embedding loading also passed in this environment. Python/package versions and
the smoke-check result are recorded in [clean-environment.json](clean-environment.json).
The warning is a TestClient dependency deprecation, not a failed application check.

## Submission checks

Before publication, inspect staged paths and scan tracked source for credential material.
Ignore OAuth client files, tokens, `.env`, local databases, backups, downloaded CVs,
virtual environments, and temporary acceptance data. Publish source, tests, setup
instructions and the sanitized acceptance report only.

GitHub Actions runs the offline suite on pushes and pull requests. The workflow's
presence is not a claim that a remote run has already completed.
