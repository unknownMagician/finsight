"""Claude adapter (official ``anthropic`` SDK, backend only).

- Q&A: every source is a *custom content* document with ``citations`` enabled, so Claude
  returns ``content_block_location`` citations (document index + block range + cited text)
  that FinSight verifies in ``app.ai.grounding``.
- Fact extraction: structured output (``output_config.format`` JSON schema); citations are not
  used there (the API rejects citations together with structured outputs), so every fact is
  verified against the page text instead.
- Refusals: server-side ``fallbacks: "default"`` (beta ``server-side-fallback-2026-07-01``); a
  final ``stop_reason == "refusal"`` raises ``AIRefusalError``.
- The system prompts are constant strings so the prompt prefix is cacheable
  (``cache_control`` auto-caching); nothing volatile is placed before the sources.
"""

import json
import logging
from typing import Any

import anthropic
from pydantic import ValidationError

from app.ai.base import (
    AIError,
    AIRateLimitedError,
    AIRefusalError,
    AnswerSegment,
    CitationRef,
    FactList,
    LLMAnswer,
    RawFact,
    Source,
)

logger = logging.getLogger("app.ai.claude")

FALLBACK_BETA = "server-side-fallback-2026-07-01"
ANSWER_MAX_TOKENS = 16000
EXTRACT_MAX_TOKENS = 16000

ANSWER_SYSTEM = """You are FinSight's equity research assistant for Indian listed companies.

Answer only from the documents provided in this conversation. They are of two kinds:
- annual-report passages uploaded by the user (cite them);
- "FinSight financial data": figures FinSight stored, each labelled with its provider, period,
  reporting basis (consolidated or standalone), currency, unit and whether it is reported or
  calculated (cite them when you use them).

Rules:
- Every number, date or factual claim must be supported by a citation to the provided documents.
- If the documents do not contain the answer, say plainly that the information is not available
  in the provided sources. Never estimate, recall from memory, or invent figures, prices,
  statements or citations.
- Keep reported figures, calculated metrics and assumptions distinct, and say which is which.
- Keep consolidated and standalone figures separate and name the basis and period you use.
- Prices in FinSight are end-of-day closes with a trading date; never describe them as live or
  real-time.
- Amounts in Indian reports are often in crore or lakh; keep the unit stated by the source.
- Do not give investment advice or buy/sell recommendations.
- Be concise: a short direct answer, then the supporting detail."""

EXTRACT_SYSTEM = """You extract financial figures from annual-report pages for FinSight.

Return only figures that are printed on the given pages. For each figure:
- quote: copy the exact text from the page that contains the number (verbatim, 1-2 lines);
- value: the number exactly as printed (keep its digits; parentheses mean negative);
- unit: the unit the page states for that figure (crores, lakhs, millions, thousands, units,
  per_share or percent). Do not convert units;
- page_number: the page the quote is on;
- basis: consolidated or standalone if the page says so, otherwise unspecified;
- period_label / period_end: the period the figure refers to, as printed.
If a requested metric is not on the pages, omit it. Never estimate or compute figures."""


def _document(source: Source) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "type": "document",
        "source": {
            "type": "content",
            "content": [{"type": "text", "text": b} for b in source.blocks],
        },
        "title": source.title,
        "citations": {"enabled": True},
    }
    if source.context:
        doc["context"] = source.context
    return doc


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    return getattr(obj, name, default) if not isinstance(obj, dict) else obj.get(name, default)


def parse_answer(response: Any, model: str) -> LLMAnswer:
    """Convert a Messages API response (SDK object) into provider-neutral segments."""
    stop_reason = str(_attr(response, "stop_reason", ""))
    if stop_reason == "refusal":
        raise AIRefusalError("the model declined to answer")
    segments: list[AnswerSegment] = []
    for block in _attr(response, "content", []) or []:
        if _attr(block, "type") != "text":
            continue  # thinking / fallback / other blocks carry no answer text
        citations = []
        for c in _attr(block, "citations", None) or []:
            if _attr(c, "type") != "content_block_location":
                continue
            citations.append(
                CitationRef(
                    source_index=int(_attr(c, "document_index", -1)),
                    start_block=int(_attr(c, "start_block_index", -1)),
                    end_block=int(_attr(c, "end_block_index", -1)),
                    cited_text=str(_attr(c, "cited_text", "")),
                )
            )
        segments.append(AnswerSegment(str(_attr(block, "text", "")), citations))
    usage = _attr(response, "usage", None)
    return LLMAnswer(
        segments=segments,
        model=str(_attr(response, "model", model)),
        stop_reason=stop_reason,
        input_tokens=int(_attr(usage, "input_tokens", 0) or 0),
        output_tokens=int(_attr(usage, "output_tokens", 0) or 0),
        request_id=_attr(response, "_request_id", None),
    )


def parse_facts(response: Any) -> list[RawFact]:
    if str(_attr(response, "stop_reason", "")) == "refusal":
        raise AIRefusalError("the model declined to extract facts")
    if str(_attr(response, "stop_reason", "")) == "max_tokens":
        raise AIError("fact extraction output was truncated")
    text = next(
        (
            _attr(b, "text", "")
            for b in _attr(response, "content", []) or []
            if _attr(b, "type") == "text"
        ),
        "",
    )
    try:
        return FactList.model_validate(json.loads(text)).facts
    except (ValueError, ValidationError) as exc:
        raise AIError("fact extraction returned invalid JSON") from exc


class ClaudeProvider:
    name = "anthropic"

    def __init__(
        self, api_key: str, *, model: str, timeout: float, client: Any | None = None
    ) -> None:
        self.model = model
        self._client = client or anthropic.Anthropic(
            api_key=api_key, timeout=timeout, max_retries=2
        )

    def _create(self, **kwargs: Any) -> Any:
        try:
            return self._client.beta.messages.create(
                model=self.model,
                betas=[FALLBACK_BETA],
                fallbacks="default",
                cache_control={"type": "ephemeral"},
                **kwargs,
            )
        except anthropic.RateLimitError as exc:
            raise AIRateLimitedError("Claude API rate limit") from exc
        except anthropic.APIStatusError as exc:
            logger.warning("claude_api_error", extra={"status": exc.status_code})
            raise AIError(f"Claude API error {exc.status_code}") from exc
        except anthropic.APIConnectionError as exc:
            raise AIError("Claude API unreachable") from exc

    def answer(self, question: str, sources: list[Source]) -> LLMAnswer:
        content: list[dict[str, Any]] = [_document(s) for s in sources]
        content.append({"type": "text", "text": question})
        response = self._create(
            max_tokens=ANSWER_MAX_TOKENS,
            system=ANSWER_SYSTEM,
            messages=[{"role": "user", "content": content}],
        )
        return parse_answer(response, self.model)

    def extract_facts(self, pages: list[tuple[int, str]], metrics: list[str]) -> list[RawFact]:
        page_text = "\n\n".join(f'<page number="{n}">\n{text}\n</page>' for n, text in pages)
        request = (
            f"{page_text}\n\nExtract these metrics where they are printed on the pages above: "
            + ", ".join(metrics)
        )
        response = self._create(
            max_tokens=EXTRACT_MAX_TOKENS,
            system=EXTRACT_SYSTEM,
            output_config={"format": {"type": "json_schema", "schema": FACT_SCHEMA}},
            messages=[{"role": "user", "content": request}],
        )
        return parse_facts(response)


FACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "metric": {"type": "string"},
                    "value": {"type": "string"},
                    "unit": {
                        "type": "string",
                        "enum": [
                            "crores",
                            "lakhs",
                            "millions",
                            "thousands",
                            "units",
                            "per_share",
                            "percent",
                        ],
                    },
                    "currency": {"type": ["string", "null"]},
                    "period_label": {"type": ["string", "null"]},
                    "period_end": {"type": ["string", "null"], "format": "date"},
                    "basis": {
                        "type": "string",
                        "enum": ["consolidated", "standalone", "unspecified"],
                    },
                    "page_number": {"type": "integer"},
                    "quote": {"type": "string"},
                },
                "required": [
                    "metric",
                    "value",
                    "unit",
                    "currency",
                    "period_label",
                    "period_end",
                    "basis",
                    "page_number",
                    "quote",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["facts"],
    "additionalProperties": False,
}
