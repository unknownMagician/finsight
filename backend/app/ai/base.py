"""Provider-neutral contracts for the AI research assistant.

The model only ever sees *sources* FinSight assembled (retrieved report passages and labelled
financial-data lines) and must cite them; every citation is re-verified by
``app.ai.grounding`` before anything reaches the user.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Protocol

from pydantic import BaseModel, Field

SourceKind = Literal["document_page", "financial_data"]


class AIError(Exception):
    """The model call failed (network, API error, malformed output)."""


class AIRateLimitedError(AIError):
    pass


class AIRefusalError(AIError):
    """The model declined the request (stop_reason == "refusal")."""


@dataclass(frozen=True)
class BlockMeta:
    """Where one citable block came from."""

    label: str  # e.g. "Annual Report FY26, p. 12" or "Revenue FY2026 (reported)"
    document_id: str | None = None
    page_number: int | None = None
    chunk_id: int | None = None


@dataclass(frozen=True)
class Source:
    title: str
    kind: SourceKind
    blocks: list[str]
    meta: list[BlockMeta]
    context: str | None = None  # shown to the model, never cited


@dataclass(frozen=True)
class CitationRef:
    source_index: int
    start_block: int
    end_block: int  # exclusive
    cited_text: str


@dataclass(frozen=True)
class AnswerSegment:
    text: str
    citations: list[CitationRef] = field(default_factory=list)


@dataclass(frozen=True)
class LLMAnswer:
    segments: list[AnswerSegment]
    model: str
    stop_reason: str
    input_tokens: int
    output_tokens: int
    request_id: str | None = None


class RawFact(BaseModel):
    """One figure as the model read it. Validated, then verified against the page text."""

    metric: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=40, description="number exactly as printed")
    unit: Literal["crores", "lakhs", "millions", "thousands", "units", "per_share", "percent"]
    currency: str | None = Field(default=None, max_length=3)
    period_label: str | None = Field(default=None, max_length=50)
    period_end: date | None = None
    basis: Literal["consolidated", "standalone", "unspecified"]
    page_number: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=600, description="verbatim text from the page")


class FactList(BaseModel):
    facts: list[RawFact] = Field(max_length=60)


class LLMProvider(Protocol):
    name: str
    model: str

    def answer(self, question: str, sources: list[Source]) -> LLMAnswer: ...

    def extract_facts(self, pages: list[tuple[int, str]], metrics: list[str]) -> list[RawFact]: ...
