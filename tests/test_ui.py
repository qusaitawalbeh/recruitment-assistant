from pathlib import Path
import requests
from streamlit.testing.v1 import AppTest
import pytest


@pytest.fixture
def connected_ui(client, monkeypatch):
    def request(method, url, **kwargs):
        kwargs.pop("timeout", None)
        kwargs.pop("stream", None)
        response = client.request(method, url.split(":8000", 1)[1], **kwargs)
        adapted = requests.Response()
        adapted.status_code = response.status_code
        adapted._content = response.content
        adapted.headers.update(response.headers)
        return adapted
    monkeypatch.setattr(requests, "request", request)
    return client


def test_jobs_page_and_create_form(connected_ui):
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30)
    app.run()
    assert not app.exception
    assert app.title[0].value == "Jobs & requirements"
    app.text_input[0].set_value("Python analyst")
    app.button[0].click().run()
    assert not app.exception
    assert any("Created Python analyst" in message.value for message in app.success)
    assert len(app.selectbox) == 1
    next(button for button in app.button if button.label == "Confirm requirements & Must-Haves").click().run()
    assert not app.exception
    assert connected_ui.get("/jobs").json()[0]["confirmed"] is True


def test_results_and_manual_decision(connected_ui, job, cv_bytes):
    response = connected_ui.post(f"/jobs/{job['id']}/screen/uploads", files={"files": ("cv.docx", cv_bytes())})
    cid = response.json()["results"][0]["candidate_id"]
    def page():
        from app import results_page
        results_page()
    app = AppTest.from_function(page, default_timeout=30).run()
    assert not app.exception
    assert app.metric[0].value == "1"
    decision = next(select for select in app.selectbox if select.label == "HR decision")
    decision.set_value("shortlist")
    next(button for button in app.button if button.label == "Save HR decision").click().run()
    assert not app.exception
    assert connected_ui.get(f"/candidates/{cid}").json()["decision"] == "shortlist"


def test_screening_page(connected_ui, job):
    def page():
        from app import screening_page
        screening_page()
    app = AppTest.from_function(page, default_timeout=30).run()
    assert not app.exception
    assert app.title[0].value == "Screen applications"
