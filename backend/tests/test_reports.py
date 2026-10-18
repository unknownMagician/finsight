"""Research reports: generation, provenance labels, owner scoping, and export formats."""

import csv
import io
import json
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.reports.render import indian_group
from tests.fixtures_ai import REPORT_PAGES, FakeLLM, make_pdf
from tests.test_calculations_api import DCF

API = "/api/v1/reports"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("123456789.5", "12,34,56,789.50"),
        ("1000", "1,000.00"),
        ("999", "999.00"),
        ("-1234567", "-12,34,567.00"),
        ("0.004", "0.00"),
    ],
)
def test_indian_grouping(value: str, expected: str) -> None:
    assert indian_group(Decimal(value)) == expected


@pytest.fixture
def prepared(client: TestClient, auth: dict[str, str]) -> FakeLLM:
    """DEMOINFO with statements, a saved DCF, and an uploaded report with extracted facts."""
    llm = FakeLLM()
    client.app.state.llm = llm  # type: ignore[attr-defined]
    client.get("/api/v1/companies", params={"q": "demo"}, headers=auth)
    assert client.post("/api/v1/companies/DEMOINFO/ingest", headers=auth).status_code == 200
    saved = {"name": "Base case", "ticker": "DEMOINFO", "inputs": DCF}
    assert client.post("/api/v1/valuations", json=saved, headers=auth).status_code == 201
    files = {"file": ("ar.pdf", make_pdf(REPORT_PAGES), "application/pdf")}
    doc = client.post(
        "/api/v1/documents",
        files=files,
        data={"title": 'AR FY26 =HYPERLINK("x") <script>alert(1)</script>', "ticker": "DEMOINFO"},
        headers=auth,
    ).json()
    assert (
        client.post(f"/api/v1/documents/{doc['id']}/facts/extract", headers=auth).status_code == 200
    )
    return llm


def sections(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {s["key"]: s for s in report["content"]["sections"]}


def test_report_contains_labelled_sourced_sections(
    client: TestClient, auth: dict[str, str], prepared: FakeLLM
) -> None:
    body = {"ticker": "DEMOINFO", "exchange": "NSE", "include_ai": True}
    r = client.post(API, json=body, headers=auth)
    assert r.status_code == 201, r.text
    report = r.json()
    assert report["includes_ai"] is True and report["ticker"] == "DEMOINFO"
    content = report["content"]
    assert content["exchange"] == "NSE" and content["basis"] == "consolidated"
    s = sections(report)
    assert all(sec["status"] == "ok" for sec in s.values()), {
        k: v["reason"] for k, v in s.items() if v["status"] != "ok"
    }

    close = s["market"]["figures"][0]
    assert close["kind"] == "market" and close["display"].startswith("₹")
    assert "demo (demo)" in close["source"]
    assert s["financials"]["tables"][0]["kind"] == "reported"
    assert s["financials"]["tables"][0]["rows"][0][:2] == ["Revenue", "12,000.00"]
    assert {f["kind"] for f in s["ratios"]["figures"]} == {"calculated"}
    assert s["dcf"]["tables"][0]["kind"] == "assumption"
    facts = s["documents"]["tables"][0]["rows"]
    assert {row[1] for row in facts} == {
        "Revenue from operations",
        "Profit after tax",
    }  # verified only
    assert s["ai"]["figures"][0]["kind"] == "ai_explanation"
    assert "[1]" in s["ai"]["paragraphs"][0]
    assert any("not investment advice" in d for d in content["disclaimers"])


def test_missing_data_is_reported_unavailable(client: TestClient, auth: dict[str, str]) -> None:
    client.get("/api/v1/companies", params={"q": "demo"}, headers=auth)
    report = client.post(API, json={"ticker": "DEMOINFO"}, headers=auth).json()
    s = sections(report)
    assert s["market"]["status"] == "unavailable"  # NSE and BSE listings: no guessing
    assert "several exchanges" in s["market"]["reason"]
    assert (
        s["financials"]["status"] == "unavailable"
        and "fetch statements" in s["financials"]["reason"]
    )
    assert s["ai"]["status"] == "unavailable" and report["includes_ai"] is False

    r = client.post(API, json={"ticker": "DEMOINFO", "include_ai": True}, headers=auth)
    assert r.status_code == 503 and r.json()["error"]["code"] == "ai_not_configured"
    assert client.post(API, json={"ticker": "NOPE"}, headers=auth).status_code == 404


def test_exports(client: TestClient, auth: dict[str, str], prepared: FakeLLM) -> None:
    report = client.post(API, json={"ticker": "DEMOINFO", "exchange": "NSE"}, headers=auth).json()
    url = f"{API}/{report['id']}/export"

    md = client.get(url, params={"format": "md"}, headers=auth)
    assert md.headers["content-type"].startswith("text/markdown")
    assert 'filename="finsight-DEMOINFO-' in md.headers["content-disposition"]
    assert "# Demo Infotech Ltd" in md.text and "## Ratios" in md.text

    page = client.get(url, params={"format": "html"}, headers=auth)
    assert "default-src 'none'" in page.text  # scripts blocked in the exported file
    assert "<script>alert(1)</script>" not in page.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page.text

    rows = list(
        csv.reader(io.StringIO(client.get(url, params={"format": "csv"}, headers=auth).text))
    )
    assert rows[0] == ["section", "item", "value", "display", "type", "period", "basis", "source"]
    injected = [r for r in rows if "HYPERLINK" in "".join(r)]
    assert injected and all(not cell.startswith("=") for r in injected for cell in r)

    data = json.loads(client.get(url, params={"format": "json"}, headers=auth).text)
    assert data["company"]["ticker"] == "DEMOINFO"
    assert client.get(url, params={"format": "exe"}, headers=auth).status_code == 422


def test_reports_are_private(
    client: TestClient,
    auth: dict[str, str],
    register_and_login: Callable[[str], dict[str, str]],
) -> None:
    client.get("/api/v1/companies", params={"q": "demo"}, headers=auth)
    report = client.post(API, json={"ticker": "DEMOBANK"}, headers=auth).json()
    mallory = register_and_login("mallory@example.com")
    assert client.get(API, headers=mallory).json() == []
    for path in (f"{API}/{report['id']}", f"{API}/{report['id']}/export"):
        assert client.get(path, headers=mallory).status_code == 404
    assert client.delete(f"{API}/{report['id']}", headers=mallory).status_code == 404
    assert [r["id"] for r in client.get(API, headers=auth).json()] == [report["id"]]
    assert client.delete(f"{API}/{report['id']}", headers=auth).status_code == 204
    assert client.get(f"{API}/{report['id']}", headers=auth).status_code == 404
