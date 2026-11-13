# 5. Evaluation

CRISP-DM phase 5. Targets: `docs/01_business_understanding.md` §1.8. Iterate on **dev**, report **test**.
Raw results: `results/<component>_<split>.json`.

## 5.1 Parser

| Version | Parser | Split | n | parse success | row count agreement | op F1 | exact match | side acc. |
|---|---|---|---|---|---|---|---|---|
| v1 | grammar | dev (synthetic) | 36 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| — | llm / hybrid | dev | — | waits for `OPENROUTER_API_KEY` | | | | |

**Iterations (grammar, dev):**
1. First run: 35/36 exact. Failure: verbose "Knit 2 together to the end of the round" — the "to the end"
   rule only covered knit/purl. Fix: generic `<op> to the end of the row/round` after phrase
   normalisation → 36/36.

**Reading the 100% honestly.** The grammar and the generator were written with the same notation
conventions, so synthetic text is the grammar's home ground; this number is an upper bound, not
evidence that it reads real patterns. The meaningful comparisons are:
- grammar vs LLM vs hybrid on the **Ravelry** patterns (free-form prose, glossaries, "work as for…"), and
- the LLM parser on synthetic text (it was not written with the generator in mind).
The test split has not been used yet.

## 5.2 Abbreviation lookup and retrieval (UC6)

`eval/eval_kb.py` on `kb_queries.jsonl`: 25 exact lookups (variants, UK terms, typos) and 25 questions.
Retrieval metrics on questions: hit@1, recall@3 (|relevant ∩ top-3| / min(3, |relevant|)), MRR.
Target (§1.8): exact accuracy ≥ 0.98, recall@3 ≥ 0.85.

**Exact / fuzzy lookup:** accuracy **1.00** on dev (15) and test (10), including typos (`sskk` → ssk,
`k2tgo` → k2tog) via fuzzy alias matching; no question is answered by the lookup path with a wrong entry.

**Question retrieval, iterations (recall@3):**

| Version | Change (one at a time) | Split | BM25 | Dense (bge-small) | Hybrid (RRF) |
|---|---|---|---|---|---|
| v1 | baseline: name + aliases + description + category/lean words | dev | 0.644 | 0.556 | 0.511 |
| v2 | BM25 stopwords ("how do I **make**…" matched "make one left"); BGE query prefix | dev | 0.667 | 0.578 | 0.567 |
| v3 | **label fix**: the two lean questions listed only 3 of 7 left-leaning / 3 of 4 right-leaning decreases; the system returned correct ones (sk2p, sssk, p2tog tbl) marked wrong | dev | 0.756 | 0.600 | 0.656 |
| v4 | **data fix**: KB descriptions lacked facts any knitter knows (M1 leaves no hole, a yo makes an eyelet, a dropped stitch forms a ladder) | dev | 0.822 | 0.622 | 0.744 |
| v4 | first look at test | **test** | 0.750 | 0.783 | 0.783 |
| v5 | light stemming (slipping → slip, stitches → stitch), motivated by the two BM25 test misses | dev | 0.900 | 0.622 | 0.778 |
| v5 | | test* | 0.683 | 0.783 | 0.783 |

\* test was looked at after v4, so v5 test numbers are not an unbiased estimate.

**What this shows.** BM25 keeps improving on the 15 dev questions (0.644 → 0.900) while dropping on test
(0.750 → 0.683): its gains partly fit the dev wording. Dense retrieval with the small embedding model is
weaker on dev but steadier; **hybrid is the most stable across splits (0.778 / 0.783) and is the default.**
None of the methods reaches the 0.85 target on test.

**Why scores are not higher:**
- KB entries are short (one or two sentences): little text for BM25 and embeddings to match a paraphrase.
- Questions often describe an effect ("without a hole", "a ladder") rather than the stitch name.
- n is small (10 test questions): one question = 0.1 hit@1.

**Next improvements (not done yet):** a larger embedding model (bge-base) for the dense part; LLM query
rewriting ("left-leaning decrease" → "ssk skp decrease leans left") before retrieval; and a **fresh
held-out question set written by the author** without looking at the KB, to replace the used test split.
