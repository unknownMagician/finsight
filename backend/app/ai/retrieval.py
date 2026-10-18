"""Deterministic BM25 retrieval over document chunks (pure; no embeddings, no network).

Numbers are kept as tokens with grouping commas removed, so "12,345" and "12345" match.
"""

import math
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

K1 = 1.5
B = 0.75
_STOP = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "were",
        "what",
        "which",
        "with",
        "how",
        "did",
        "does",
        "do",
        "much",
        "many",
        "company",
    ]
)


def tokenize(text: str) -> list[str]:
    text = re.sub(r"(?<=\d),(?=\d)", "", text.lower())
    return [t for t in re.findall(r"[a-z]+|\d+(?:\.\d+)?", text) if t not in _STOP]


@dataclass(frozen=True)
class Candidate:
    key: object  # caller's identifier (e.g. chunk id)
    text: str


@dataclass(frozen=True)
class Hit:
    key: object
    score: float


def bm25(query: str, candidates: Sequence[Candidate], limit: int) -> list[Hit]:
    terms = tokenize(query)
    if not terms or not candidates:
        return []
    docs = [tokenize(c.text) for c in candidates]
    n = len(docs)
    avg_len = sum(len(d) for d in docs) / n or 1.0
    df: Counter[str] = Counter()
    for d in docs:
        df.update(set(d))
    hits: list[Hit] = []
    for candidate, tokens in zip(candidates, docs, strict=True):
        tf = Counter(tokens)
        score = 0.0
        for term in set(terms):
            if term not in tf:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            freq = tf[term]
            score += idf * freq * (K1 + 1) / (freq + K1 * (1 - B + B * len(tokens) / avg_len))
        if score > 0:
            hits.append(Hit(candidate.key, score))
    hits.sort(key=lambda h: (-h.score, str(h.key)))
    return hits[:limit]
