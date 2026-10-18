"""Test helpers for documents and the AI assistant: a minimal PDF writer and a scripted LLM.
All report text is SYNTHETIC."""

from typing import Literal

from app.ai.base import (
    AIRefusalError,
    AnswerSegment,
    CitationRef,
    LLMAnswer,
    RawFact,
    Source,
)

REPORT_PAGES = [
    "Demo Infotech Ltd\nAnnual Report 2025-26\nSYNTHETIC TEST DOCUMENT",
    "Directors Report\nThe Board is pleased to present the results for FY2025-26.\n"
    "Revenue from operations was Rs. 12,345.60 crore, up 10% year on year.",
    "Consolidated Statement of Profit and Loss (Rs. crore)\n"
    "Profit after tax 2,160.25\nBasic EPS (Rs.) 54.01",
    "Risk factors\nCurrency fluctuations and client concentration are key risks.",
]


def _escape(line: str) -> str:
    return line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(pages: list[str]) -> bytes:
    """A valid PDF with one Helvetica text page per entry ("" = page without a text layer)."""
    objects: list[bytes] = []
    page_ids = [4 + 2 * i for i in range(len(pages))]
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for index, text in enumerate(pages):
        ops = ["BT", "/F1 11 Tf", "72 720 Td", "14 TL"]
        ops += [f"({_escape(line)}) Tj T*" for line in text.split("\n") if text]
        ops.append("ET")
        stream = "\n".join(ops).encode("latin-1")
        objects.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {page_ids[index] + 1} 0 R >>"
            ).encode()
        )
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    ).encode()
    return out


Mode = Literal["grounded", "partial", "refuse"]


class FakeLLM:
    """Scripted stand-in for ClaudeProvider. Cites the first block of the first source."""

    name = "fake"
    model = "fake-model"

    def __init__(self) -> None:
        self.mode: Mode = "grounded"
        self.answer_calls: list[tuple[str, list[Source]]] = []
        self.extract_calls: list[tuple[list[tuple[int, str]], list[str]]] = []

    def answer(self, question: str, sources: list[Source]) -> LLMAnswer:
        self.answer_calls.append((question, sources))
        if self.mode == "refuse":
            raise AIRefusalError("declined")
        first = sources[0].blocks[0]
        segments = [
            AnswerSegment("According to the sources, "),
            AnswerSegment(
                "revenue was Rs. 12,345.60 crore",
                [CitationRef(0, 0, 1, first[: min(len(first), 80)])],
            ),
            AnswerSegment("."),
        ]
        if self.mode == "partial":
            segments.append(AnswerSegment(" Margins were 99%."))  # uncited figure
            segments.append(
                AnswerSegment(" EBITDA rose.", [CitationRef(0, 0, 1, "text that is not there")])
            )
        return LLMAnswer(segments, self.model, "end_turn", 1000, 50)

    def extract_facts(self, pages: list[tuple[int, str]], metrics: list[str]) -> list[RawFact]:
        self.extract_calls.append((pages, metrics))
        return [
            RawFact(
                metric="Revenue from operations",
                value="12,345.60",
                unit="crores",
                currency="INR",
                period_label="FY2025-26",
                basis="unspecified",
                page_number=2,
                quote="Revenue from operations was Rs. 12,345.60 crore",
            ),
            RawFact(
                metric="Profit after tax",
                value="2,160.25",
                unit="crores",
                currency="INR",
                basis="consolidated",
                page_number=3,
                quote="Profit after tax 2,160.25",
            ),
            RawFact(  # hallucinated: the quote is not on the page
                metric="EBITDA",
                value="4,000",
                unit="crores",
                basis="unspecified",
                page_number=3,
                quote="EBITDA 4,000",
            ),
            RawFact(  # value not in its own quote
                metric="Basic EPS",
                value="55.00",
                unit="per_share",
                basis="consolidated",
                page_number=3,
                quote="Basic EPS (Rs.) 54.01",
            ),
        ]
