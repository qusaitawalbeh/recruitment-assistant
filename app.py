"""Streamlit pages using the FastAPI backend through requests."""
import os
from pathlib import Path
import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
API_URL = os.getenv("API_URL", "http://127.0.0.1:8000").rstrip("/")
st.set_page_config(page_title="Recruitment Assistant", page_icon="📋", layout="wide")


def api(method, path, **kwargs):
    try:
        response = requests.request(method, f"{API_URL}{path}", timeout=(5, 1800), **kwargs)
        if not response.ok:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            st.error(f"Request failed ({response.status_code}): {detail}")
            st.stop()
        return response if kwargs.get("stream") else response.json()
    except requests.RequestException as exc:
        st.error(f"Cannot reach the backend. Start uvicorn src.api:app --reload. Details: {exc}")
        st.stop()


def select_job():
    jobs = api("GET", "/jobs")
    if not jobs:
        st.info("Create a job first on the Jobs & requirements page.")
        st.stop()
    job_ids = [job["id"] for job in jobs]
    selected = st.selectbox("Job", job_ids, format_func=lambda i: next(
        f"{j['title']} · {j['id'][:8]}" for j in jobs if j["id"] == i))
    return next(job for job in jobs if job["id"] == selected)


def jobs_page():
    st.title("Jobs & requirements")
    st.write("Enter a job description, review the extracted criteria, and choose what is essential.")
    with st.expander("Create a job", expanded=True):
        with st.form("new_job"):
            title = st.text_input("Job title")
            sample = Path(__file__).parent / "data" / "job_description.txt"
            description = st.text_area("Job description", height=240,
                                       value=sample.read_text(encoding="utf-8"))
            submitted = st.form_submit_button("Extract requirements", type="primary")
        if submitted:
            with st.spinner("Extracting requirements with Ollama..."):
                created = api("POST", "/jobs", json={"title": title, "description": description})
            st.success(f"Created {created['title']}. Review and confirm its requirements below.")
    job = select_job()
    with st.expander("Original job description"):
        st.text(job["description"])
    st.subheader("Review the criteria")
    st.caption("AI output needs your review. Check Must-Have for essential criteria; other criteria "
               "contribute to the preferred score. Add, edit or remove rows as needed. "
               "Use numeric minimum_years only for experience criteria.")
    columns = ["id", "text", "category", "must_have", "minimum_years"]
    frame = pd.DataFrame(job["requirements"], columns=columns)
    edited = st.data_editor(frame, num_rows="dynamic", hide_index=True,
                            key=f"requirements-{job['id']}-{job['revision']}",
                            column_config={
                                "must_have": st.column_config.CheckboxColumn("Must-Have", default=False),
                                "category": st.column_config.SelectboxColumn("Category", options=[
                                    "skill", "experience", "education", "language", "certification"]),
                                "text": st.column_config.TextColumn("Requirement", width="large"),
                                "minimum_years": st.column_config.NumberColumn("Minimum years", min_value=0., max_value=80.),
                            }, width="stretch")
    st.caption("Saving criteria makes previous results stale. Re-screen them on the Screening page.")
    if st.button("Confirm requirements & Must-Haves", type="primary"):
        rows = edited.astype(object).where(pd.notna(edited), None).to_dict("records")
        for index, row in enumerate(rows, 1):
            row["id"] = row.get("id") or f"custom-{index}"
            row["must_have"] = bool(row.get("must_have"))
        api("PUT", f"/jobs/{job['id']}/requirements", json={"requirements": rows})
        st.success("Requirements confirmed. You can screen applications now.")


def show_processing(result):
    rows = result.get("results", [])
    counts = {status: sum(row["status"] == status for row in rows)
              for status in ("processed", "duplicate", "error")}
    st.write(f"Processed: {counts['processed']} · Duplicates: {counts['duplicate']} · Errors: {counts['error']}")
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    else:
        st.info("No supported attachments or stored candidates were found.")


def screening_page():
    st.title("Screen applications")
    job = select_job()
    if not job["confirmed"]:
        st.info("Confirm this job's requirements before screening.")
        st.stop()
    st.subheader("Upload CVs")
    files = st.file_uploader("PDF or DOCX · up to 10 MB each", type=["pdf", "docx"],
                             accept_multiple_files=True)
    if st.button("Screen uploaded CVs", disabled=not files, type="primary"):
        with st.spinner("Reading CVs and checking each requirement. This can take several minutes..."):
            result = api("POST", f"/jobs/{job['id']}/screen/uploads",
                         files=[("files", (f.name, f.getvalue(), f.type)) for f in files])
        show_processing(result)
    st.subheader("Collect from Gmail")
    st.caption("Use a job-specific subject, label, or address so applications are linked to this job. "
               "Gmail access is read-only. A browser may open for first-time OAuth consent.")
    query = st.text_input("Gmail search", placeholder='subject:"Junior Data Scientist" newer_than:30d')
    maximum = st.number_input("Maximum emails", min_value=1, max_value=500, value=50)
    if st.button("Collect & screen Gmail CVs", disabled=not query.strip()):
        with st.spinner("Collecting Gmail attachments and screening..."):
            result = api("POST", f"/jobs/{job['id']}/screen/gmail",
                         json={"query": query, "max_results": maximum})
        show_processing(result)
    st.subheader("Re-screen saved applications")
    st.write("Use this after editing requirements or fixing a model issue. HR decisions are preserved.")
    if st.button("Re-screen saved CVs"):
        with st.spinner("Re-screening..."):
            show_processing(api("POST", f"/jobs/{job['id']}/rescreen"))


def candidate_table(candidates):
    return pd.DataFrame([{
        "Rank": c.get("rank"), "Name": c["info"].get("candidate_name") or c["filename"],
        "Preferred score (%)": c["score"], "Missing must-haves": len(c["missing_must_haves"]),
        "HR decision": c["decision"], "Needs re-screening": c.get("stale", False),
        "Candidate ID": c["id"],
    } for c in candidates])


def results_page():
    st.title("Results & HR review")
    st.caption("Screening supports your review. Scores are matching aids; HR makes every decision.")
    job = select_job()
    top_n = st.number_input("Top candidates to display", min_value=1, max_value=500, value=20)
    data = api("GET", f"/jobs/{job['id']}/candidates", params={"top_n": top_n})
    stats = data["statistics"]
    for column, key, label in zip(st.columns(4), ["total", "qualified", "needs_review", "stale"],
                                  ["Applications", "Meet all must-haves", "Need review", "Need re-screening"]):
        column.metric(label, stats[key])
    top, qualified, review = st.tabs(["Top candidates", "All qualified", "Must-have gaps / stale"])
    for tab, group in [(top, "top_candidates"), (qualified, "qualified"), (review, "review")]:
        with tab:
            if data[group]:
                st.dataframe(candidate_table(data[group]), hide_index=True, width="stretch")
            else:
                st.info("No candidates in this group.")
    all_candidates = data["qualified"] + data["review"]
    if not all_candidates:
        return
    st.subheader("Candidate details")
    candidates = {c["id"]: c for c in all_candidates}
    selected = st.selectbox("Candidate", list(candidates), format_func=lambda i: (
        f"{candidates[i]['info'].get('candidate_name') or candidates[i]['filename']} · {i[:8]}"))
    candidate = api("GET", f"/candidates/{selected}")
    if candidate["stale"]:
        st.warning("These results use older criteria. Re-screen before relying on the score.")
    if not candidate["semantic_enabled"]:
        st.info("Semantic embeddings were disabled for this screening.")
    st.write("Application source:", candidate["source"])
    with st.expander("Extracted candidate information"):
        st.json(candidate["info"])
    for match in candidate["matches"]:
        with st.expander(f"{'Must-Have' if match['must_have'] else 'Preferred'} · {match['text']} · {match['status'].replace('_', ' ')}"):
            st.write(match["explanation"])
            if match["evidence"]:
                st.text(match["evidence"])
            else:
                st.write("No evidence found.")
            if match["semantic"]:
                st.caption(f"Cosine similarity: {match['semantic']['similarity']:.3f}. "
                           "Similarity is context, not proof that a requirement is satisfied.")
                st.text(match["semantic"]["passage"])
    if st.button("Load original CV", key=f"load-{selected}"):
        response = api("GET", f"/candidates/{selected}/cv", stream=True)
        st.session_state[f"cv-{selected}"] = (response.content, response.headers.get("content-type"))
    if f"cv-{selected}" in st.session_state:
        content, media_type = st.session_state[f"cv-{selected}"]
        st.download_button("Download / open original CV", content,
                            file_name=candidate["filename"], mime=media_type)
    decisions = ["review_later", "shortlist", "reject"]
    decision = st.selectbox("HR decision", decisions, index=decisions.index(candidate["decision"]),
                            format_func=lambda value: value.replace("_", " ").title(), key=f"decision-{selected}")
    if st.button("Save HR decision", type="primary"):
        api("PATCH", f"/candidates/{selected}/decision", json={"decision": decision})
        st.success("HR decision saved.")
        st.rerun()


def main():
    st.navigation([
        st.Page(jobs_page, title="Jobs & requirements", icon="📋"),
        st.Page(screening_page, title="Screening", icon="📥"),
        st.Page(results_page, title="Results & HR review", icon="👥"),
    ]).run()


if __name__ == "__main__":
    main()
