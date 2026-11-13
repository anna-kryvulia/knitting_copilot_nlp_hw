"""Knitting Copilot — Streamlit UI.

Phase 4 (in progress): Pattern tab (paste → parse → row-by-row simulation) and abbreviation lookup.
Run: streamlit run app.py
"""

import json

import pandas as pd
import streamlit as st

from knit_copilot import kb
from knit_copilot.components import explainer, parser
from knit_copilot.config import ROOT, settings
from knit_copilot.display import row_lines
from knit_copilot.retrieval import search as kbsearch
from knit_copilot.simulator import simulate

st.set_page_config(page_title="Knitting Copilot", page_icon="🧶", layout="wide")


@st.cache_data
def example_patterns() -> dict[str, dict]:
    cases = [json.loads(line) for line in open(ROOT / "data" / "eval" / "parse_cases.jsonl", encoding="utf-8")]
    picked = {}
    for c in cases:                         # one example per template x style, dev split only
        key = f"{c['expected']['ir']['title']} — {c['tags'][1]}"
        if c["split"] == "dev" and key not in picked:
            picked[key] = {"text": c["input"]["text"], "size": c["input"]["size"]}
    return dict(sorted(picked.items()))


# ---------- sidebar: abbreviation lookup (UC6) ----------
with st.sidebar:
    st.header("Abbreviations")
    q = st.text_input("Abbreviation or question", placeholder="ssk, yfwd … or “how do I decrease left?”")

    def show_entry(a: kb.Abbreviation, title_prefix: str = "") -> None:
        st.subheader(f"{title_prefix}{a.id} — {a.name}")
        st.write(a.description)
        if a.is_stitch_op:
            st.caption(f"Uses {a.consumes} st, makes {a.produces} st"
                       + (f" · leans {a.lean}" if a.lean else "")
                       + (f" · UK: {a.uk_term}" if a.uk_term else ""))
        st.caption(f"Source: {a.reference}")

    if q:
        with st.spinner("Searching…"):
            hits = kbsearch.search(q)
        abbrs = kb.abbreviations()
        if hits and hits[0].method in ("exact", "fuzzy"):
            if hits[0].method == "fuzzy":
                st.info(f"No exact match for “{q}” — did you mean **{hits[0].id}**?")
            show_entry(abbrs[hits[0].id])
        elif hits:
            st.caption("Closest entries:")
            for h in hits[:3]:
                show_entry(abbrs[h.id])
        else:
            st.warning(f"“{q}” is not in the knowledge base.")
    st.divider()
    st.caption(f"LLM: {settings.llm_model}" if settings.openrouter_api_key else
               "LLM: no OPENROUTER_API_KEY — grammar parser only")

st.title("🧶 Knitting Copilot")
tab_pattern, = st.tabs(["Pattern"])

# ---------- Pattern tab ----------
with tab_pattern:
    examples = example_patterns()
    left, right = st.columns([2, 3])
    with left:
        choice = st.selectbox("Load an example", ["—"] + list(examples))
        default = examples[choice]["text"] if choice != "—" else ""
        text = st.text_area("Pattern text", value=default, height=420, key=f"text-{choice}")
        has_key = bool(settings.openrouter_api_key)
        mode = st.radio("Parser", ["hybrid", "llm"] if has_key else ["hybrid"], horizontal=True,
                        help="hybrid: grammar first, LLM only if the grammar can't read the text. "
                             "llm: always the language model (needs OPENROUTER_API_KEY).")
        if not has_key:
            st.caption("LLM mode needs OPENROUTER_API_KEY in .env (restart the app after adding it).")
        go = st.button("Read pattern", type="primary", disabled=not text.strip())

    with right:
        if go:
            with st.spinner("Reading the pattern…"):
                out = parser.run(parser.ParserInput(text=text, mode=mode))
            st.session_state["parsed"] = out
            st.session_state["explanation"] = None
        out = st.session_state.get("parsed")
        if out is not None:
            if not out.ok:
                st.error("Could not read this pattern.")
                for w in out.warnings:
                    st.caption(w)
            else:
                p = out.pattern
                size = None
                if p.sizes:
                    size = st.selectbox("Size", p.sizes)
                sim = simulate(p, size)
                cols = st.columns(4)
                cols[0].metric("Construction", p.construction)
                cols[1].metric("Cast on", sim.cast_on)
                cols[2].metric("Rows / rounds", len(sim.rows))
                cols[3].metric("Read by", out.method)
                if p.gauge:
                    st.caption(f"Gauge: {p.gauge.sts_per_10cm} sts"
                               + (f" × {p.gauge.rows_per_10cm} rows" if p.gauge.rows_per_10cm else "")
                               + " per 10 cm" + (f" on {p.gauge.needle_mm} mm needles" if p.gauge.needle_mm else ""))
                if sim.errors:
                    st.error("The stitch counts don't work out: " + sim.errors[0])
                mism = sim.count_mismatches()
                if mism:
                    st.warning("Stated counts that differ from the computed ones: "
                               + ", ".join(f"{r.label} (says {r.stated_count}, computed {r.end_count})" for r in mism))
                for w in out.warnings:
                    st.caption(f"⚠ {w}")
                rows_tab, explain_tab = st.tabs(["Rows", "Explanation"])
                with rows_tab:
                    every = st.toggle("Show every row", value=False,
                                      help="Off: repeated rows are grouped into one line. On: one line per row worked.")
                    df = pd.DataFrame([{
                        "Rows": ln.rows, "Instruction": ln.instruction, "Side": ln.side, "Stitches": ln.stitches,
                        "Stated": ln.stated, "Worked as": ln.worked_as}
                        for ln in row_lines(p, sim, grouped=not every)])
                    st.dataframe(df, hide_index=True, use_container_width=True, height=520,
                                 column_config={"Worked as": st.column_config.TextColumn(width="large")})
                with explain_tab:
                    focus = st.text_input("Focus (optional)", placeholder="e.g. Row 3, the crown decreases …",
                                          help="Leave empty to explain the whole pattern.")
                    can_explain = bool(settings.openrouter_api_key)
                    if st.button("Explain", type="primary", disabled=not can_explain):
                        with st.spinner("Writing the explanation (free models can take up to a minute)…"):
                            try:
                                st.session_state["explanation"] = explainer.run(
                                    explainer.ExplainerInput(pattern=p, size=size, focus=focus or None))
                            except (RuntimeError, ValueError) as e:
                                st.session_state["explanation"] = None
                                st.error(f"Could not get an explanation: {e}")
                    if not can_explain:
                        st.caption("Needs OPENROUTER_API_KEY in .env.")
                    exp = st.session_state.get("explanation")
                    if exp is not None:
                        if exp.violations:
                            st.warning("Some details could not be verified against the pattern: "
                                       + "; ".join(exp.violations[:3]))
                        st.markdown(exp.text)
                        with st.expander("Facts the explanation is based on (computed by code)"):
                            st.code(exp.facts, language=None)
