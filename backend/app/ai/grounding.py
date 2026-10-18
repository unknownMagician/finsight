"""Verify model output against the sources it was given (pure).

- Answer citations: the cited block range must exist and the cited text must occur in those
  blocks (whitespace/quote-insensitive). Invalid citations are removed and reported.
- A segment containing a figure (any digit) without a valid citation is flagged
  ``uncited_figure``; the UI shows it as unsupported.
- Extracted facts: the quote must occur on the stated page, and the value must appear as a
  number in the quote. Otherwise the fact is ``unverified`` and is never used as data.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Literal

from app.ai.base import AnswerSegment, CitationRef, LLMAnswer, RawFact, Source

GroundingStatus = Literal["grounded", "partially_grounded", "ungrounded"]

# Typographic quotes, dashes and the minus sign, keyed by code point.
_PUNCT = str.maketrans(
    {0x2018: "'", 0x2019: "'", 0x201C: '"', 0x201D: '"', 0x2013: "-", 0x2014: "-", 0x2212: "-"}
)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_PUNCT)
    return re.sub(r"\s+", " ", text).strip().lower()


def has_figure(text: str) -> bool:
    return bool(re.search(r"\d", text))


@dataclass(frozen=True)
class GroundingIssue:
    code: str  # invalid_citation | uncited_figure | no_citations
    segment_index: int
    message: str


@dataclass(frozen=True)
class GroundedAnswer:
    segments: list[AnswerSegment]
    status: GroundingStatus
    issues: list[GroundingIssue] = field(default_factory=list)


def _citation_valid(citation: CitationRef, sources: list[Source]) -> bool:
    if not 0 <= citation.source_index < len(sources):
        return False
    blocks = sources[citation.source_index].blocks
    if not 0 <= citation.start_block < citation.end_block <= len(blocks):
        return False
    haystack = normalize(" ".join(blocks[citation.start_block : citation.end_block]))
    needle = normalize(citation.cited_text)
    return bool(needle) and needle in haystack


def ground_answer(answer: LLMAnswer, sources: list[Source]) -> GroundedAnswer:
    segments: list[AnswerSegment] = []
    issues: list[GroundingIssue] = []
    valid_total = 0
    for index, segment in enumerate(answer.segments):
        valid = [c for c in segment.citations if _citation_valid(c, sources)]
        if len(valid) < len(segment.citations):
            issues.append(
                GroundingIssue(
                    "invalid_citation",
                    index,
                    "A citation did not match its source and was removed.",
                )
            )
        if not valid and has_figure(segment.text):
            issues.append(
                GroundingIssue(
                    "uncited_figure",
                    index,
                    "This passage contains a figure without a verifiable source.",
                )
            )
        valid_total += len(valid)
        segments.append(AnswerSegment(segment.text, valid))
    substantive = any(s.text.strip() for s in segments)
    if valid_total == 0 and substantive:
        status: GroundingStatus = "ungrounded"
        issues.append(GroundingIssue("no_citations", -1, "The answer cites no source."))
    elif issues:
        status = "partially_grounded"
    else:
        status = "grounded"
    return GroundedAnswer(segments, status, issues)


def parse_value(raw: str) -> Decimal | None:
    """A printed number: grouping commas removed; "(1,234)" and "-1234" are negative."""
    text = raw.strip().replace(",", "").translate(_PUNCT)
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    if not value.is_finite():
        return None
    return -value if negative else value


def _magnitudes(text: str) -> set[Decimal]:
    found: set[Decimal] = set()
    for match in re.finditer(r"\d[\d,]*(?:\.\d+)?", text):
        try:
            found.add(Decimal(match.group(0).replace(",", "")))
        except InvalidOperation:
            continue
    return found


@dataclass(frozen=True)
class FactCheck:
    value: Decimal | None
    status: Literal["verified", "unverified"]
    note: str | None


def verify_fact(fact: RawFact, page_text: str | None) -> FactCheck:
    value = parse_value(fact.value)
    if value is None:
        return FactCheck(None, "unverified", f"value {fact.value!r} is not a number")
    if page_text is None:
        return FactCheck(value, "unverified", f"page {fact.page_number} does not exist")
    if normalize(fact.quote) not in normalize(page_text):
        return FactCheck(value, "unverified", "quote not found on the cited page")
    if abs(value) not in _magnitudes(fact.quote):
        return FactCheck(value, "unverified", "value does not appear in the quote")
    return FactCheck(value, "verified", None)
