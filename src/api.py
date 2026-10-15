"""Local FastAPI backend: run uvicorn src.api:app --reload."""
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, Query
from fastapi.responses import FileResponse, JSONResponse
from . import ai_extractor, database, screening
from .matcher import rank_candidates
from .models import (JobCreate, RequirementsUpdate, DecisionUpdate, GmailRequest,
                     JobResponse, CandidateResponse, BatchResponse, GmailResponse,
                     RankingResponse, HealthResponse)

app = FastAPI(title="Recruitment Screening Assistant", version="2.0.0")


@app.exception_handler(KeyError)
async def missing_record(request, exc):
    return JSONResponse(status_code=404, content={"detail": str(exc.args[0])})


@app.exception_handler(ValueError)
async def invalid_input(request, exc):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(RuntimeError)
async def dependency_failure(request, exc):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/health", response_model=HealthResponse)
def health():
    return {"status": "ok"}


@app.get("/jobs", response_model=list[JobResponse])
def jobs():
    return database.list_jobs()


@app.post("/jobs", status_code=201, response_model=JobResponse)
def create_job(payload: JobCreate):
    extracted = ai_extractor.extract_job_requirements(payload.description)
    requirements = screening.requirements_from_extraction(extracted, payload.description)
    return database.create_job(payload.title, payload.description, requirements)


@app.get("/jobs/{job_id}", response_model=JobResponse)
def job(job_id: str):
    return database.get_job(job_id)


@app.put("/jobs/{job_id}/requirements", response_model=JobResponse)
def update_requirements(job_id: str, payload: RequirementsUpdate):
    return database.update_requirements(job_id, [r.model_dump() for r in payload.requirements])


@app.post("/jobs/{job_id}/screen/uploads", response_model=BatchResponse, response_model_exclude_none=True)
def upload_cvs(job_id: str, files: list[UploadFile] = File(...)):
    job = screening.ready_job(job_id)
    results = []
    for file in files:
        try:
            content = file.file.read(screening.MAX_FILE_BYTES + 1)
            results.append(screening.ingest(job, file.filename or "", content, {"type": "upload"}))
        except Exception as exc:
            results.append({"filename": file.filename, "status": "error", "error": str(exc)})
        finally:
            file.file.close()
    return {"results": results}


@app.post("/jobs/{job_id}/screen/gmail", response_model=GmailResponse, response_model_exclude_none=True)
def gmail(job_id: str, payload: GmailRequest):
    try:
        return screening.screen_gmail(job_id, payload.query, payload.max_results)
    except (KeyError, ValueError):
        raise
    except Exception as exc:
        raise RuntimeError(f"Gmail processing failed: {exc}") from exc


@app.post("/jobs/{job_id}/rescreen", response_model=BatchResponse, response_model_exclude_none=True)
def rescreen(job_id: str):
    return {"results": screening.rescreen(job_id)}


def public_candidate(candidate):
    return {key: value for key, value in candidate.items() if key not in {"cv_path", "cv_text", "file_hash"}}


@app.get("/jobs/{job_id}/candidates", response_model=RankingResponse)
def candidates(job_id: str, top_n: int = Query(20, ge=1, le=500)):
    job = database.get_job(job_id)
    result = rank_candidates(database.list_candidates(job_id), job["revision"], top_n)
    for group in ("qualified", "review", "top_candidates"):
        result[group] = [public_candidate(c) for c in result[group]]
    return result


@app.get("/candidates/{candidate_id}", response_model=CandidateResponse)
def candidate_detail(candidate_id: str):
    candidate = database.get_candidate(candidate_id)
    candidate["stale"] = candidate["job_revision"] != database.get_job(candidate["job_id"])["revision"]
    return public_candidate(candidate)


@app.patch("/candidates/{candidate_id}/decision", response_model=CandidateResponse)
def decide(candidate_id: str, payload: DecisionUpdate):
    database.update_decision(candidate_id, payload.decision)
    return candidate_detail(candidate_id)


@app.get("/candidates/{candidate_id}/cv")
def original_cv(candidate_id: str):
    from fastapi import HTTPException
    candidate = database.get_candidate(candidate_id)
    path = Path(candidate["cv_path"]).resolve()
    cv_dir = (database.data_dir() / "cvs").resolve()
    if not path.is_relative_to(cv_dir) or not path.is_file():
        raise HTTPException(404, "Original CV is unavailable")
    media_type = "application/pdf" if path.suffix == ".pdf" else (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    return FileResponse(path, filename=candidate["filename"], media_type=media_type)
