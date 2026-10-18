"""Documents (owner-scoped uploads + AI fact extraction) and the AI research endpoint."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from tests.fixtures_ai import REPORT_PAGES, FakeLLM, make_pdf

DOCS = "/api/v1/documents"
ASK = "/api/v1/research/ask"


@pytest.fixture
def llm(client: TestClient) -> FakeLLM:
    fake = FakeLLM()
    client.app.state.llm = fake  # type: ignore[attr-defined]
    return fake


@pytest.fixture
def demo_company(client: TestClient, auth: dict[str, str]) -> None:
    assert client.get("/api/v1/companies", params={"q": "demo"}, headers=auth).status_code == 200


def upload(
    client: TestClient,
    auth: dict[str, str],
    pages: list[str] = REPORT_PAGES,
    **form: Any,
) -> Any:
    files = {"file": ("ar-2026.pdf", make_pdf(pages), "application/pdf")}
    data = {"title": "Annual Report FY26", **form}
    return client.post(DOCS, files=files, data=data, headers=auth)


def test_upload_list_page_delete(
    client: TestClient, auth: dict[str, str], demo_company: None
) -> None:
    r = upload(client, auth, ticker="DEMOINFO", fiscal_year="2026")
    assert r.status_code == 201, r.text
    doc = r.json()
    assert (doc["page_count"], doc["pages_with_text"], doc["status"]) == (4, 4, "ready")
    assert doc["company"]["ticker"] == "DEMOINFO" and doc["facts"] == []

    page = client.get(f"{DOCS}/{doc['id']}/pages/2", headers=auth).json()
    assert "12,345.60 crore" in page["text"]
    assert client.get(f"{DOCS}/{doc['id']}/pages/9", headers=auth).status_code == 404
    listed = client.get(DOCS, params={"ticker": "DEMOINFO"}, headers=auth).json()
    assert [d["id"] for d in listed] == [doc["id"]]

    dup = upload(client, auth)
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "document_exists"
    assert client.delete(f"{DOCS}/{doc['id']}", headers=auth).status_code == 204
    assert client.get(f"{DOCS}/{doc['id']}", headers=auth).status_code == 404


def test_upload_validation(
    client: TestClient, auth: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    not_pdf = client.post(
        DOCS,
        files={"file": ("x.pdf", b"PK\x03\x04zip", "application/pdf")},
        data={"title": "x"},
        headers=auth,
    )
    assert not_pdf.status_code == 422 and not_pdf.json()["error"]["code"] == "invalid_pdf"

    scanned = upload(client, auth, pages=["", ""])
    assert scanned.status_code == 201 and scanned.json()["status"] == "no_text"

    monkeypatch.setenv("FINSIGHT_UPLOAD_MAX_MB", "1")
    get_settings.cache_clear()
    big = client.post(
        DOCS,
        files={"file": ("big.pdf", b"%PDF-1.4\n" + b"0" * (1024 * 1024 + 10), "application/pdf")},
        data={"title": "big"},
        headers=auth,
    )
    assert big.status_code == 413 and big.json()["error"]["code"] == "file_too_large"
    assert (
        client.post(
            DOCS, files={"file": ("a.pdf", make_pdf(["a"]))}, data={"title": "a"}
        ).status_code
        == 401
    )


def test_documents_are_private(
    client: TestClient,
    auth: dict[str, str],
    register_and_login: Callable[[str], dict[str, str]],
    llm: FakeLLM,
) -> None:
    doc = upload(client, auth).json()
    eve = register_and_login("eve@example.com")
    url = f"{DOCS}/{doc['id']}"
    assert client.get(DOCS, headers=eve).json() == []
    for request in (
        lambda: client.get(url, headers=eve),
        lambda: client.get(f"{url}/pages/1", headers=eve),
        lambda: client.post(f"{url}/facts/extract", headers=eve),
        lambda: client.delete(url, headers=eve),
    ):
        assert request().status_code == 404
    r = client.post(ASK, json={"question": "revenue?", "document_ids": [doc["id"]]}, headers=eve)
    assert r.status_code == 404
    assert llm.extract_calls == [] and llm.answer_calls == []  # no AI spend on others' data
    assert client.get(url, headers=auth).status_code == 200
    # The same file can be uploaded independently by another user.
    assert upload(client, eve).status_code == 201


def test_fact_extraction_verifies_every_figure(
    client: TestClient, auth: dict[str, str], llm: FakeLLM
) -> None:
    doc = upload(client, auth).json()
    r = client.post(f"{DOCS}/{doc['id']}/facts/extract", headers=auth)
    assert r.status_code == 200, r.text
    facts = {f["metric"]: f for f in r.json()["facts"]}
    assert facts["Revenue from operations"]["status"] == "verified"
    assert facts["Revenue from operations"]["value"] == "12345.600000"
    assert facts["Profit after tax"]["status"] == "verified"
    assert facts["EBITDA"]["status"] == "unverified"  # quote not on the page
    assert facts["EBITDA"]["verification_note"] == "quote not found on the cited page"
    assert facts["Basic EPS"]["verification_note"] == "value does not appear in the quote"
    assert {f["kind"] for f in facts.values()} == {"extracted"}
    pages_sent = [n for n, _ in llm.extract_calls[0][0]]
    assert 2 in pages_sent and 3 in pages_sent  # BM25-selected relevant pages

    # Re-extraction replaces rather than duplicates.
    again = client.post(f"{DOCS}/{doc['id']}/facts/extract", headers=auth).json()
    assert len(again["facts"]) == 4

    scanned = upload(client, auth, pages=[""]).json()
    r = client.post(f"{DOCS}/{scanned['id']}/facts/extract", headers=auth)
    assert r.status_code == 422 and r.json()["error"]["code"] == "no_text"


def test_ai_endpoints_without_api_key(client: TestClient, auth: dict[str, str]) -> None:
    doc = upload(client, auth).json()
    r = client.post(f"{DOCS}/{doc['id']}/facts/extract", headers=auth)
    assert r.status_code == 503 and r.json()["error"]["code"] == "ai_not_configured"
    assert client.post(ASK, json={"question": "revenue?"}, headers=auth).status_code == 503
    status = client.get("/api/v1/research/status", headers=auth).json()
    assert status == {"configured": False, "provider": None, "model": None}


def test_research_answer_is_grounded_in_documents_and_data(
    client: TestClient, auth: dict[str, str], llm: FakeLLM, demo_company: None
) -> None:
    upload(client, auth, ticker="DEMOINFO")
    assert client.post("/api/v1/companies/DEMOINFO/ingest", headers=auth).status_code == 200
    r = client.post(
        ASK,
        json={"question": "What was revenue from operations?", "ticker": "demoinfo"},
        headers=auth,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "ai_explanation" and body["grounding"] == "grounded"
    assert body["model"] == "fake-model" and "Not investment advice" in body["disclaimer"]
    kinds = [s["kind"] for s in body["sources"]]
    assert kinds[0] == "document_page" and kinds[-1] == "financial_data"
    cited = body["segments"][1]["citations"][0]
    assert cited["source"] == 1 and cited["page_number"] == 2
    assert cited["cited_text"].startswith("Directors Report")

    _question, sources = llm.answer_calls[0]
    data_source = sources[-1]
    assert any("Revenue, FY2026" in b and "Reported; source demo" in b for b in data_source.blocks)
    assert any("Calculated by FinSight" in b for b in data_source.blocks)


def test_research_flags_unsupported_claims_and_refusals(
    client: TestClient, auth: dict[str, str], llm: FakeLLM
) -> None:
    doc = upload(client, auth).json()
    llm.mode = "partial"
    body = client.post(
        ASK, json={"question": "revenue and margins?", "document_ids": [doc["id"]]}, headers=auth
    ).json()
    assert body["grounding"] == "partially_grounded"
    codes = {i["code"] for i in body["issues"]}
    assert codes == {"uncited_figure", "invalid_citation"}
    assert body["segments"][-1]["citations"] == []  # fabricated citation removed

    llm.mode = "refuse"
    r = client.post(ASK, json={"question": "revenue?", "document_ids": [doc["id"]]}, headers=auth)
    assert r.status_code == 422 and r.json()["error"]["code"] == "ai_refused"


def test_research_without_sources_does_not_call_the_model(
    client: TestClient, auth: dict[str, str], llm: FakeLLM, demo_company: None
) -> None:
    r = client.post(
        ASK, json={"question": "What is the outlook?", "ticker": "DEMOSTEEL"}, headers=auth
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "no_sources"
    assert llm.answer_calls == []
    assert client.post(ASK, json={"question": "x"}, headers=auth).status_code == 422  # too short
