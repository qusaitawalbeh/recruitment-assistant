from src.api import app


def test_all_json_routes_publish_response_contracts(client):
    routes = [route for route in app.routes if getattr(route, "path", "").startswith(("/jobs", "/candidates", "/health"))]
    for route in routes:
        if route.path.endswith("/cv"):
            continue
        assert route.response_model is not None, route.path
    schema = client.get("/openapi.json").json()
    assert schema["paths"]["/jobs"]["post"]["responses"]["201"]["content"]["application/json"]["schema"]["$ref"].endswith("JobResponse")


def test_candidate_response_does_not_expose_internal_document_fields(client, job, cv_bytes):
    item = client.post(f"/jobs/{job['id']}/screen/uploads", files={"files": ("cv.docx", cv_bytes())}).json()["results"][0]
    candidate = client.get(f"/candidates/{item['candidate_id']}").json()
    assert {"cv_path", "cv_text", "file_hash", "result"}.isdisjoint(candidate)
