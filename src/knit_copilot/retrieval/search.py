"""Abbreviation knowledge-base search (UC6): exact/fuzzy lookup + BM25, embedding and hybrid retrieval.

Purpose: answer "what is ssk" (lookup, typo-tolerant) and "how do I make a left-leaning decrease?" (retrieval).
Input: a query string. Output: ranked KB entry ids with scores and the method that found them.
Model calls: none (local sentence-transformers embedding model, no LLM). Tool calls: none.

Methods compared in eval/eval_kb.py:
  bm25    lexical match over name + aliases + description + category/lean words
  dense   cosine similarity of sentence embeddings (EMBEDDING_MODEL, default BAAI/bge-small-en-v1.5)
  hybrid  reciprocal rank fusion of bm25 and dense (k = 60)
`search()` first tries an exact or fuzzy abbreviation match; only questions go to retrieval.
Default method: hybrid. BM25 was best on dev but dropped on test (overfitting to 15 dev questions);
hybrid is stable across splits (dev 0.778 / test 0.783 recall@3). See docs/05_evaluation.md §5.2.
"""

from __future__ import annotations

import difflib
import re
from functools import lru_cache
from typing import Literal

import numpy as np
from pydantic import BaseModel
from rank_bm25 import BM25Okapi

from knit_copilot import kb
from knit_copilot.config import settings

Method = Literal["bm25", "dense", "hybrid"]
RRF_K = 60
FUZZY_CUTOFF = 0.75
# Question words carry no meaning for BM25 ("how do I make…" otherwise matches "make one left").
STOPWORDS = {"how", "do", "does", "i", "a", "an", "the", "what", "which", "is", "it", "to", "my", "can", "should",
             "mean", "means", "of", "on", "in", "for", "why", "with", "and", "at", "make", "use", "you", "this",
             "that", "or", "be", "are", "so", "when", "there", "way", "way", "get", "once"}
# BGE models expect this instruction in front of queries (not documents).
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class Hit(BaseModel):
    id: str
    score: float
    method: str


def _stem(word: str) -> str:
    """Light suffix stripping so 'slipping'/'slipped'/'slips' → 'slip', 'stitches' → 'stitch'.
    Abbreviations with digits (k2tog, c6b) are left alone."""
    if any(ch.isdigit() for ch in word) or len(word) <= 3:
        return word
    for suffix in ("ing", "ed"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            word = word[: -len(suffix)]
            if len(word) > 3 and word[-1] == word[-2] and word[-1] not in "lsz":   # slipp → slip
                word = word[:-1]
            return word
    if word.endswith(("ches", "shes", "sses", "xes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _tokens(text: str, drop_stopwords: bool = False) -> list[str]:
    toks = re.findall(r"[a-z0-9/]+", text.lower())
    if drop_stopwords:
        toks = [t for t in toks if t not in STOPWORDS]
    return [_stem(t) for t in toks]


def _document(a: kb.Abbreviation) -> str:
    """Searchable text for one entry. Category and lean are spelled out so questions like
    'which decrease leans left' match entries whose description doesn't use those words."""
    extra = []
    if a.category not in ("term", "marker"):
        extra.append(a.category)
    if a.lean:
        extra += [f"leans {a.lean}", f"{a.lean}-leaning", f"{a.lean} leaning"]
    if a.consumes is not None and a.produces is not None:
        if a.produces > a.consumes:
            extra.append(f"adds {a.produces - a.consumes} stitch increase")
        elif a.produces < a.consumes:
            extra.append(f"removes {a.consumes - a.produces} stitch decrease")
    return " ".join([a.name, *a.aliases, a.uk_term or "", a.description, *extra])


@lru_cache
def _index() -> tuple[list[str], BM25Okapi, list[str]]:
    entries = list(kb.abbreviations().values())
    docs = [_document(a) for a in entries]
    return [a.id for a in entries], BM25Okapi([_tokens(d) for d in docs]), docs


@lru_cache
def _encoder():
    from sentence_transformers import SentenceTransformer   # heavy import, only when dense search is used
    return SentenceTransformer(settings.embedding_model)


@lru_cache
def _doc_embeddings() -> np.ndarray:
    _, _, docs = _index()
    return _encoder().encode(docs, normalize_embeddings=True)


def lookup_exact(query: str) -> Hit | None:
    """Exact alias match, then a fuzzy match on aliases for typos (sskk → ssk, k2tgo → k2tog)."""
    a = kb.lookup(query)
    if a:
        return Hit(id=a.id, score=1.0, method="exact")
    q = kb.normalise(query).replace(" ", "")
    if not q or " " in query.strip() and len(query.split()) > 3:      # a sentence, not a typo
        return None
    keys = list(kb.alias_index())
    match = difflib.get_close_matches(q, keys, n=1, cutoff=FUZZY_CUTOFF)
    if match:
        return Hit(id=kb.alias_index()[match[0]], score=round(difflib.SequenceMatcher(None, q, match[0]).ratio(), 3),
                   method="fuzzy")
    return None


def _bm25(query: str) -> list[tuple[str, float]]:
    ids, bm25, _ = _index()
    scores = bm25.get_scores(_tokens(query, drop_stopwords=True))
    return sorted(zip(ids, scores), key=lambda x: -x[1])


def _dense(query: str) -> list[tuple[str, float]]:
    ids, _, _ = _index()
    prefix = QUERY_PREFIX if "bge" in settings.embedding_model.lower() else ""
    q = _encoder().encode([prefix + query], normalize_embeddings=True)[0]
    scores = _doc_embeddings() @ q
    return sorted(zip(ids, scores.tolist()), key=lambda x: -x[1])


def retrieve(query: str, method: Method = "hybrid", k: int = 5) -> list[Hit]:
    if method == "bm25":
        return [Hit(id=i, score=round(s, 4), method="bm25") for i, s in _bm25(query)[:k]]
    if method == "dense":
        return [Hit(id=i, score=round(s, 4), method="dense") for i, s in _dense(query)[:k]]
    fused: dict[str, float] = {}
    for ranking in (_bm25(query), _dense(query)):
        for rank, (i, _) in enumerate(ranking):
            fused[i] = fused.get(i, 0.0) + 1.0 / (RRF_K + rank + 1)
    best = sorted(fused.items(), key=lambda x: -x[1])[:k]
    return [Hit(id=i, score=round(s, 5), method="hybrid") for i, s in best]


def search(query: str, method: Method = "hybrid", k: int = 5) -> list[Hit]:
    """Exact/fuzzy abbreviation first (one hit), otherwise retrieval."""
    hit = lookup_exact(query)
    if hit:
        return [hit]
    return retrieve(query, method, k)
