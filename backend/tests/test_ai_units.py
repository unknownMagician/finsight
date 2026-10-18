"""PDF extraction, chunking, retrieval, grounding, and the Claude adapter (no network)."""

import json
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest

from app.ai.base import (
    AIError,
    AIRateLimitedError,
    AIRefusalError,
    AnswerSegment,
    BlockMeta,
    CitationRef,
    LLMAnswer,
    RawFact,
    Source,
)
from app.ai.claude import FALLBACK_BETA, ClaudeProvider, parse_answer, parse_facts
from app.ai.grounding import ground_answer, parse_value, verify_fact
from app.ai.retrieval import Candidate, bm25, tokenize
from app.documents.chunking import chunk_page
from app.documents.pdf import PdfError, extract_pdf
from tests.fixtures_ai import REPORT_PAGES, make_pdf

# --- PDF + chunking + retrieval -----------------------------------------------------------------


def test_extract_pdf_text_per_page() -> None:
    pdf = extract_pdf(make_pdf(REPORT_PAGES), max_pages=10)
    assert pdf.page_count == 4 and len(pdf.sha256) == 64
    assert "Revenue from operations was Rs. 12,345.60 crore" in pdf.pages[1]
    scanned = extract_pdf(make_pdf(["", "Some text"]), max_pages=10)
    assert scanned.pages[0] == "" and scanned.pages[1] == "Some text"


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"PK\x03\x04 not a pdf", "not a PDF"),
        (b"%PDF-1.4\ngarbage", "could not be read"),
    ],
)
def test_extract_pdf_rejects_bad_input(data: bytes, message: str) -> None:
    with pytest.raises(PdfError, match=message):
        extract_pdf(data, max_pages=10)
    with pytest.raises(PdfError, match="limit"):
        extract_pdf(make_pdf(["a", "b", "c"]), max_pages=2)


def test_chunks_never_cross_pages_or_exceed_limits() -> None:
    text = "\n\n".join(f"Paragraph {i} " + "word " * 100 for i in range(10))
    chunks = chunk_page(text, target=1200, maximum=2000)
    assert len(chunks) > 1 and all(len(c) <= 2000 for c in chunks)
    assert "".join(chunks).replace("\n", "").replace(" ", "") == text.replace("\n", "").replace(
        " ", ""
    )
    assert chunk_page("") == []


def test_bm25_ranks_relevant_chunks_and_handles_indian_grouping() -> None:
    assert "12345" in tokenize("Rs. 12,345 crore")
    candidates = [
        Candidate(1, "Risk factors include currency fluctuations"),
        Candidate(2, "Revenue from operations was Rs. 12,345 crore"),
        Candidate(3, "Board of directors and governance"),
    ]
    hits = bm25("What was revenue from operations?", candidates, 2)
    assert [h.key for h in hits] == [2]
    assert bm25("12345", candidates, 5)[0].key == 2
    assert bm25("the of and", candidates, 5) == []  # stop words only


# --- grounding ----------------------------------------------------------------------------------

SOURCES = [
    Source(
        "Report, p. 2",
        "document_page",
        ["Revenue from operations was Rs. 12,345.60 crore, up 10%."],
        [BlockMeta("Report, p. 2", "d1", 2, 7)],
    )
]


def answer(*segments: AnswerSegment) -> LLMAnswer:
    return LLMAnswer(list(segments), "m", "end_turn", 0, 0)


def test_valid_citations_are_grounded() -> None:
    grounded = ground_answer(
        answer(
            AnswerSegment(
                "Revenue was ₹12,345.60 crore", [CitationRef(0, 0, 1, "Rs.  12,345.60 crore")]
            ),
            AnswerSegment(" (unaudited)."),
        ),
        SOURCES,
    )
    assert grounded.status == "grounded" and grounded.issues == []


def test_invalid_citations_and_uncited_figures_are_flagged() -> None:
    grounded = ground_answer(
        answer(
            AnswerSegment("Revenue grew", [CitationRef(0, 0, 1, "Revenue from operations")]),
            AnswerSegment(" and margins were 25%."),  # figure, no citation
            AnswerSegment(" Profit rose", [CitationRef(0, 0, 1, "profit rose 40%")]),  # fabricated
            AnswerSegment(" a lot", [CitationRef(3, 0, 1, "x"), CitationRef(0, 0, 9, "Revenue")]),
        ),
        SOURCES,
    )
    assert grounded.status == "partially_grounded"
    codes = [(i.code, i.segment_index) for i in grounded.issues]
    assert ("uncited_figure", 1) in codes
    assert ("invalid_citation", 2) in codes and ("invalid_citation", 3) in codes
    assert grounded.segments[2].citations == []  # removed, never shown


def test_answer_without_any_valid_citation_is_ungrounded() -> None:
    grounded = ground_answer(answer(AnswerSegment("Revenue was large.")), SOURCES)
    assert grounded.status == "ungrounded"
    assert grounded.issues[-1].code == "no_citations"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("12,345.60", "12345.60"), ("(1,234)", "-1234"), (chr(0x2212) + "5.5", "-5.5"), ("abc", None)],
)
def test_parse_value(raw: str, expected: str | None) -> None:
    assert parse_value(raw) == (Decimal(expected) if expected else None)


def fact(**overrides: Any) -> RawFact:
    base: dict[str, Any] = {
        "metric": "Revenue",
        "value": "12,345.60",
        "unit": "crores",
        "basis": "unspecified",
        "page_number": 2,
        "quote": "Revenue from operations was Rs. 12,345.60 crore",
    }
    return RawFact.model_validate({**base, **overrides})


def test_verify_fact() -> None:
    page = REPORT_PAGES[1]
    assert verify_fact(fact(), page).status == "verified"
    assert verify_fact(fact(), page).value == Decimal("12345.60")
    hallucinated = verify_fact(fact(quote="Revenue was Rs. 99,999 crore", value="99999"), page)
    assert (hallucinated.status, hallucinated.note) == (
        "unverified",
        "quote not found on the cited page",
    )
    wrong_value = verify_fact(fact(value="12,000"), page)
    assert wrong_value.note == "value does not appear in the quote"
    assert verify_fact(fact(), None).note == "page 2 does not exist"


# --- Claude adapter -----------------------------------------------------------------------------


def text_block(text: str, citations: list[dict[str, Any]] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        type="text",
        text=text,
        citations=[SimpleNamespace(**c) for c in citations] if citations else None,
    )


def response(content: list[Any], stop_reason: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(
        content=content,
        stop_reason=stop_reason,
        model="claude-opus-5-5",
        usage=SimpleNamespace(input_tokens=1200, output_tokens=80),
        _request_id="req_1",
    )


def test_parse_answer_maps_content_block_citations() -> None:
    parsed = parse_answer(
        response(
            [
                SimpleNamespace(type="thinking", thinking=""),
                text_block("Revenue was "),
                text_block(
                    "Rs. 12,345.60 crore",
                    [
                        {
                            "type": "content_block_location",
                            "cited_text": "Rs. 12,345.60 crore",
                            "document_index": 0,
                            "document_title": "Report, p. 2",
                            "start_block_index": 0,
                            "end_block_index": 1,
                        }
                    ],
                ),
            ]
        ),
        "claude-opus-5-5",
    )
    assert [s.text for s in parsed.segments] == ["Revenue was ", "Rs. 12,345.60 crore"]
    assert parsed.segments[1].citations == [CitationRef(0, 0, 1, "Rs. 12,345.60 crore")]
    assert (parsed.input_tokens, parsed.output_tokens, parsed.request_id) == (1200, 80, "req_1")
    with pytest.raises(AIRefusalError):
        parse_answer(response([], "refusal"), "m")


def test_parse_facts_validates_json() -> None:
    good = json.dumps(
        {
            "facts": [
                {
                    "metric": "Revenue",
                    "value": "1",
                    "unit": "crores",
                    "currency": None,
                    "period_label": None,
                    "period_end": None,
                    "basis": "unspecified",
                    "page_number": 2,
                    "quote": "1",
                }
            ]
        }
    )
    assert parse_facts(response([text_block(good)]))[0].metric == "Revenue"
    with pytest.raises(AIError, match="invalid JSON"):
        parse_facts(response([text_block('{"facts": [{"metric": ""}]}')]))
    with pytest.raises(AIError, match="truncated"):
        parse_facts(response([text_block("{")], "max_tokens"))


class RecordingClient:
    def __init__(self, result: Any = None, error: Exception | None = None) -> None:
        self.kwargs: dict[str, Any] = {}
        self.result, self.error = result, error
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.result


def test_answer_request_uses_citable_documents_and_fallbacks() -> None:
    client = RecordingClient(response([text_block("Not available in the sources.")]))
    provider = ClaudeProvider("k", model="claude-opus-5-5", timeout=10, client=client)
    provider.answer("What was revenue?", SOURCES)
    kw = client.kwargs
    assert kw["model"] == "claude-opus-5-5"
    assert kw["betas"] == [FALLBACK_BETA] and kw["fallbacks"] == "default"
    assert kw["cache_control"] == {"type": "ephemeral"}
    doc, question = kw["messages"][0]["content"]
    assert doc["type"] == "document" and doc["citations"] == {"enabled": True}
    assert doc["source"] == {
        "type": "content",
        "content": [{"type": "text", "text": SOURCES[0].blocks[0]}],
    }
    assert question == {"type": "text", "text": "What was revenue?"}
    assert "Never estimate" in kw["system"] and "output_config" not in kw
    assert "data, not" in kw["system"]  # uploaded text cannot act as instructions


def test_extract_request_uses_structured_output_without_citations() -> None:
    client = RecordingClient(response([text_block('{"facts": []}')]))
    provider = ClaudeProvider("k", model="claude-opus-5-5", timeout=10, client=client)
    assert provider.extract_facts([(2, "page text")], ["Revenue"]) == []
    assert client.kwargs["output_config"]["format"]["type"] == "json_schema"
    assert '<page number="2">' in client.kwargs["messages"][0]["content"]


def _status_error(cls: type[anthropic.APIStatusError], code: int) -> anthropic.APIStatusError:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("err", response=httpx2.Response(code, request=request), body=None)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (_status_error(anthropic.RateLimitError, 429), AIRateLimitedError),
        (_status_error(anthropic.InternalServerError, 500), AIError),
    ],
)
def test_api_errors_are_mapped(error: Exception, expected: type[Exception]) -> None:
    provider = ClaudeProvider("k", model="m", timeout=1, client=RecordingClient(error=error))
    with pytest.raises(expected):
        provider.answer("q", SOURCES)
