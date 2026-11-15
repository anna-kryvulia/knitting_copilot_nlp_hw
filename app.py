"""Knitting Copilot — Streamlit UI.

Tabs: My project (setup → working pattern → row tracker, chat via the LangGraph graph), Pattern explorer,
Yarn; sidebar: abbreviation lookup. Theme: .streamlit/config.toml + the CSS below.
Run: streamlit run app.py
"""

import json

import pandas as pd
import streamlit as st

from knit_copilot import charts, db, gauge, kb, project, tracker
from knit_copilot import graph as chat_graph
from knit_copilot.components import explainer, parser, rewriter, yarn_advisor, yarn_linker
from knit_copilot.config import ROOT, settings
from knit_copilot.display import row_lines
from knit_copilot.retrieval import search as kbsearch
from knit_copilot.simulator import simulate
from knit_copilot.tracing import get_trace

st.set_page_config(page_title="Knitting Copilot", page_icon="🧶", layout="wide")

# Look: light, warm background with a yarn-red accent (colours in .streamlit/config.toml).
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,650&family=Nunito+Sans:wght@400;600;700&display=swap');
:root { --kc-red: #C8283C; --kc-red-soft: #F8E1E3; --kc-line: #E6D9CC; --kc-card: #FFFFFF; }
.block-container { padding-top: 3.4rem; max-width: 1280px; }
h1, h2, h3 { letter-spacing: -0.01em; }
.kc-hero { display: flex; align-items: center; gap: 1rem; padding: 1.1rem 1.4rem; margin-bottom: 0.6rem;
  background: var(--kc-card); border: 1px solid var(--kc-line); border-left: 6px solid var(--kc-red);
  border-radius: 0.9rem; box-shadow: 0 2px 10px rgba(80, 40, 30, 0.05); }
.kc-hero .kc-ball { font-size: 2.4rem; line-height: 1; }
.kc-hero h1 { font-family: 'Fraunces', serif; font-size: 2rem; margin: 0; padding: 0; color: #2E2522; }
.kc-hero p { margin: 0.15rem 0 0; color: #7A6A62; font-size: 0.98rem; }
.kc-hero .kc-tag { margin-left: auto; background: var(--kc-red-soft); color: #A81F31; font-weight: 700;
  font-size: 0.78rem; padding: 0.3rem 0.7rem; border-radius: 999px; white-space: nowrap; }
/* tabs: red underline and bold active tab */
.stTabs [data-baseweb="tab-list"] { gap: 0.4rem; border-bottom: 1px solid var(--kc-line); }
.stTabs [data-baseweb="tab"] { padding: 0.5rem 0.9rem; border-radius: 0.6rem 0.6rem 0 0; }
.stTabs [aria-selected="true"] { background: var(--kc-red-soft); }
.stTabs [aria-selected="true"] p { color: #A81F31; font-weight: 700; }
/* cards: bordered containers, expanders, metrics, chat */
[data-testid="stVerticalBlockBorderWrapper"] { background: var(--kc-card); }
[data-testid="stExpander"] details { background: var(--kc-card); border-radius: 0.7rem; }
[data-testid="stMetric"] { background: var(--kc-card); border: 1px solid var(--kc-line); border-radius: 0.7rem;
  padding: 0.6rem 0.8rem; }
[data-testid="stMetricValue"] { color: var(--kc-red); }
[data-testid="stChatMessage"] { background: var(--kc-card); border: 1px solid var(--kc-line); border-radius: 0.9rem; }
[data-testid="stSidebar"] h2 { font-family: 'Fraunces', serif; }
.stButton button[kind="primary"] { box-shadow: 0 2px 6px rgba(200, 40, 60, 0.25); }
.stProgress > div > div > div > div { background-color: var(--kc-red); }
/* knit texture: rows of V stitches */
.kc-hero { position: relative; overflow: hidden; }
.kc-hero::after { content: ""; position: absolute; inset: 0 0 0 45%; pointer-events: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='26' height='22'%3E%3Cg fill='%23C8283C' fill-opacity='0.13'%3E%3Cellipse cx='8' cy='11' rx='4' ry='9' transform='rotate(-28 8 11)'/%3E%3Cellipse cx='18' cy='11' rx='4' ry='9' transform='rotate(28 18 11)'/%3E%3C/g%3E%3C/svg%3E");
  -webkit-mask-image: linear-gradient(to left, #000 30%, transparent); mask-image: linear-gradient(to left, #000 30%, transparent); }
.kc-hero > * { position: relative; z-index: 1; }
.kc-stats { display: flex; gap: 0.5rem; margin-top: 0.55rem; flex-wrap: wrap; }
.kc-stat { background: #FBF7F2; border: 1px solid var(--kc-line); border-radius: 999px; padding: 0.15rem 0.65rem;
  font-size: 0.8rem; color: #5E4F48; }
.kc-stat b { color: var(--kc-red); }
/* section cards, steps and tiles */
.kc-card { background: var(--kc-card); border: 1px solid var(--kc-line); border-radius: 0.9rem; padding: 1.1rem 1.3rem;
  box-shadow: 0 2px 10px rgba(80, 40, 30, 0.04); margin-bottom: 0.9rem; }
.kc-card h3 { font-family: 'Fraunces', serif; font-size: 1.25rem; margin: 0 0 0.2rem; padding: 0; }
.kc-card .kc-sub { color: #7A6A62; font-size: 0.92rem; margin: 0 0 0.9rem; }
.kc-steps { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.8rem; }
.kc-step { background: #FBF7F2; border: 1px solid var(--kc-line); border-radius: 0.8rem; padding: 0.9rem; }
.kc-step .kc-num { display: inline-flex; width: 1.7rem; height: 1.7rem; border-radius: 50%; background: var(--kc-red);
  color: #fff; font-weight: 700; align-items: center; justify-content: center; font-size: 0.9rem; }
.kc-step.kc-done .kc-num { background: #2E7D4F; }
.kc-step.kc-todo { border-color: #EBC2C7; background: #FDF3F4; }
.kc-step h4 { margin: 0.5rem 0 0.2rem; font-size: 1rem; padding: 0; }
.kc-step p { margin: 0; font-size: 0.86rem; color: #6E5F58; }
.kc-tiles { display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.7rem; }
.kc-tile { display: flex; gap: 0.7rem; align-items: flex-start; background: #FBF7F2; border: 1px solid var(--kc-line);
  border-radius: 0.8rem; padding: 0.8rem; }
.kc-tile .kc-ico { font-size: 1.4rem; width: 2.3rem; height: 2.3rem; border-radius: 0.6rem; background: var(--kc-red-soft);
  display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.kc-tile b { display: block; font-size: 0.95rem; }
.kc-tile span { font-size: 0.84rem; color: #6E5F58; }
.kc-chips { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-top: 0.4rem; }
.kc-chip { background: var(--kc-red-soft); color: #A81F31; border-radius: 999px; padding: 0.2rem 0.7rem; font-size: 0.82rem; }
.kc-side-brand { display: flex; align-items: center; gap: 0.5rem; padding: 0.6rem 0.7rem; margin-bottom: 0.8rem;
  background: #fff; border: 1px solid var(--kc-line); border-left: 4px solid var(--kc-red); border-radius: 0.7rem; }
.kc-side-brand b { font-family: 'Fraunces', serif; font-size: 1.05rem; }
.kc-side-brand span { display: block; font-size: 0.76rem; color: #7A6A62; }
.kc-summary { background: #FBF7F2; border: 1px solid var(--kc-line); border-radius: 0.7rem; padding: 0.6rem 0.9rem;
  margin: 0.2rem 0 0.8rem; }
.kc-summary b { display: block; } .kc-summary span { font-size: 0.86rem; color: #6E5F58; }
.kc-now-row { padding: 0.3rem 0 0.8rem; }
.kc-now-row .kc-label { font-size: 0.85rem; font-weight: 700; color: var(--kc-red); text-transform: uppercase;
  letter-spacing: 0.04em; }
.kc-now-row .kc-instr { font-family: 'Fraunces', serif; font-size: 1.9rem; line-height: 1.25; margin: 0.25rem 0; }
.kc-now-row .kc-counts { color: #6E5F58; font-size: 0.95rem; }
@media (max-width: 900px) { .kc-steps, .kc-tiles { grid-template-columns: 1fr; } .kc-hero .kc-tag { display: none; } }
</style>
""", unsafe_allow_html=True)


def html(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def tiles(items: list[tuple[str, str, str]]) -> str:
    return '<div class="kc-tiles">' + "".join(
        f'<div class="kc-tile"><div class="kc-ico">{i}</div><div><b>{t}</b><span>{d}</span></div></div>'
        for i, t, d in items) + "</div>"


def rng(a: float, b: float, unit: str) -> str:
    return f"{a:g} {unit}" if a == b else f"{a:g}–{b:g} {unit}"


def chips(words: list[str]) -> str:
    return '<div class="kc-chips">' + "".join(f'<span class="kc-chip">{w}</span>' for w in words) + "</div>"


def current_project() -> "project.Project | None":
    """The project chosen in the My project tab (or the newest one)."""
    pid = st.session_state.get("project_id")
    if pid is None:
        projects = db.list_projects()
        pid = projects[0][0] if projects else None
    return db.load(pid) if pid else None


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
    html('<div class="kc-side-brand">📖<div><b>Stitch dictionary</b>'
         f'<span>{len(kb.abbreviations())} abbreviations · US and UK terms</span></div></div>')
    pick = st.pills("Popular", ["k2tog", "ssk", "yo", "m1l", "sl1", "pm", "kfb", "psso"], label_visibility="collapsed")
    q = st.text_input("Abbreviation or question", value=pick or "",
                      placeholder="ssk, yfwd … or “how do I decrease left?”")

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

st.markdown("""
<div class="kc-hero">
  <div class="kc-ball">🧶</div>
  <div><h1>Knitting Copilot</h1>
  <p>Reads your pattern, fits it to your yarn and gauge, draws the chart and keeps count of your rows.</p>
  <div class="kc-stats"><span class="kc-stat"><b>NLP</b> pattern reading</span>
  <span class="kc-stat"><b>%d</b> yarns from Ukrainian shops</span>
  <span class="kc-stat"><b>mm · cm</b> metric only</span></div></div>
  <div class="kc-tag">every number checked by code</div>
</div>
""" % len(yarn_linker.yarns()), unsafe_allow_html=True)
tab_project, tab_pattern, tab_yarn = st.tabs(["🧶\u2002My project", "📜\u2002Pattern explorer", "🐑\u2002Yarn"])

# ---------- Pattern tab ----------
with tab_pattern:
    examples = example_patterns()
    left, right = st.columns([2, 3])
    with left:
        choice = st.selectbox("Load an example", ["—"] + list(examples))
        default = examples[choice]["text"] if choice != "—" else ""
        text = st.text_area("Pattern text", value=default, height=420, key=f"text-{choice}")
        has_key = bool(settings.openrouter_api_key)
        go = st.button("Read pattern", type="primary", disabled=not text.strip(), use_container_width=True)
        with st.expander("Reading options"):
            mode = st.radio("Parser", ["hybrid", "llm"] if has_key else ["hybrid"], horizontal=True,
                            help="hybrid: grammar first, LLM only if the grammar can't read the text. "
                                 "llm: always the language model.")
            if not has_key:
                st.caption("LLM mode needs an API key in .env (restart the app after adding it).")

    with right:
        if go:
            with st.spinner("Reading the pattern…"):
                out = parser.run(parser.ParserInput(text=text, mode=mode))
            st.session_state["parsed"] = out
            st.session_state["explorer_text"] = text if out.ok else None
            st.session_state["explanation"] = None
            st.session_state["adjustment"] = None
            st.session_state["rewrite"] = None
        out = st.session_state.get("parsed")
        if out is None:
            html('<div class="kc-card"><h3>Paste a pattern, get the whole picture</h3>'
                 '<p class="kc-sub">Load an example on the left or paste your own written pattern, then press '
                 '<b>Read pattern</b>.</p>' + tiles([
                     ("🔢", "Rows", "every row worked, with stitch counts checked by the simulator"),
                     ("🟥", "Chart", "a knitting chart drawn from the written rows"),
                     ("💬", "Explanation", "plain-English walkthrough with stitch-dictionary sources"),
                     ("📏", "My gauge", "the pattern recalculated for your swatch, repeats kept whole")])
                 + '<p class="kc-sub" style="margin:0.9rem 0 0.2rem">Understands notation like</p>'
                 + chips(["*k2, p2; rep from *", "k to last 3 sts", "rep rnds 1–4 3 more times",
                          "until piece measures 12 cm", "S (M, L)", "sm, ssk"]) + "</div>")
        if out is not None:
            if not out.ok:
                st.error("Could not read this pattern.")
                for w in out.warnings:
                    st.caption(w)
            else:
                p = out.pattern
                size = None
                top1, top2 = st.columns([2, 1], vertical_alignment="bottom")
                if p.sizes:
                    size = top1.selectbox("Size", p.sizes)
                cur_pr = current_project()
                if cur_pr is not None and cur_pr.stage == "setup" and st.session_state.get("explorer_text"):
                    if top2.button(f"➕ Use in “{cur_pr.name}”", use_container_width=True,
                                   help="Adds this pattern (and the chosen size) to your project in My project."):
                        res = project.set_pattern(cur_pr, st.session_state["explorer_text"])
                        if res.ok and size:
                            project.select_size(cur_pr, size)
                        db.save(cur_pr)
                        st.session_state.pop(f"step-{cur_pr.id}", None)
                        (st.success if res.ok else st.warning)(
                            (res.message + " Open the My project tab to continue.") if res.ok else res.message)
                est_rows = None
                if parser.NO_ROW_GAUGE in out.warnings:
                    est_rows = round(1.4 * p.gauge.sts_per_10cm, 1) if p.gauge else 28.0
                sim = simulate(p, size, rows_per_10cm=est_rows)
                cols = st.columns(4)
                cols[0].metric("Construction", p.construction)
                cols[1].metric("Cast on", sim.cast_on)
                cols[2].metric("Rows / rounds", len(sim.rows))
                cols[3].metric("Read by", "Rules" if out.method.startswith("grammar") else "AI model",
                               help=f"Parser method: {out.method}")
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
                    st.caption(f"⚠ {w}" + (f" (shown here with a typical {est_rows:g} rows per 10 cm)"
                                           if w == parser.NO_ROW_GAUGE else ""))
                rows_tab, chart_tab, explain_tab, gauge_tab = st.tabs(["Rows", "Chart", "Explanation", "My gauge"])
                with chart_tab:
                    written = [r.label for st_ in p.pieces[0].steps if hasattr(st_, "rows") for r in st_.rows]
                    default_labels = charts.default_rows(p, size)
                    chosen = st.multiselect("Rows to chart", written, default=[x for x in default_labels if x in written],
                                            help="Default: the block with the most stitch work.")
                    mode = st.radio("Width", ["auto", "full width", "one repeat"], horizontal=True,
                                    help="auto: one repeat (red box) when the row is wider than 48 stitches")
                    if chosen:
                        ch = charts.build(p, size, labels=[x for x in written if x in chosen],
                                          motif={"auto": None, "full width": False, "one repeat": True}[mode])
                        png = charts.render_png(ch)
                        st.image(png, use_container_width=ch.width > 20)
                        st.caption("Read right-side rows (numbers on the right) from right to left and wrong-side "
                                   "rows (numbers on the left) from left to right. Grey = no stitch.")
                        st.download_button("Download chart (PNG)", png, file_name="chart.png", mime="image/png")
                with rows_tab:
                    every = st.toggle("Show every row", value=False,
                                      help="Off: repeated rows are grouped into one line. On: one line per row worked.")
                    df = pd.DataFrame([{
                        "Rows": ln.rows, "Pattern row": ln.instruction, "Side": ln.side, "Stitches": ln.stitches,
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
                with gauge_tab:
                    if not p.gauge:
                        st.info("This pattern states no gauge, so it cannot be adjusted.")
                    else:
                        st.caption(f"Pattern gauge: {p.gauge.sts_per_10cm:g} sts"
                                   + (f" × {p.gauge.rows_per_10cm:g} rows" if p.gauge.rows_per_10cm else "")
                                   + " per 10 cm. Enter your swatch (after blocking):")
                        g1, g2, g3 = st.columns(3)
                        k_sts = g1.number_input("Your stitches / 10 cm", min_value=1.0, max_value=60.0,
                                                value=float(p.gauge.sts_per_10cm), step=0.5)
                        k_rows = g2.number_input("Your rows / 10 cm", min_value=0.0, max_value=80.0,
                                                 value=float(p.gauge.rows_per_10cm or 0), step=0.5,
                                                 help="0 = not measured")
                        k_needle = g3.number_input("Your needles (mm)", min_value=0.0, max_value=25.0,
                                                   value=float(p.gauge.needle_mm or 0), step=0.25)
                        if st.button("Adjust to my gauge", type="primary"):
                            try:
                                st.session_state["adjustment"] = gauge.adjust(p, size, gauge.KnitterGauge(
                                    sts_per_10cm=k_sts, rows_per_10cm=k_rows or None, needle_mm=k_needle or None))
                                st.session_state["rewrite"] = None
                            except ValueError as e:
                                st.error(str(e))
                        adj = st.session_state.get("adjustment")
                        if adj is not None:
                            if not adj.ok:
                                st.error(" ".join(adj.notes))
                            else:
                                d1, d2, d3 = st.columns(3)
                                d1.metric("Cast on", adj.chosen_stitches,
                                          delta=adj.chosen_stitches - adj.changes[0].old)
                                d2.metric("Width", f"{adj.after.width_cm:g} cm",
                                          delta=f"{adj.after.width_cm - adj.before.width_cm:+.1f} cm", delta_color="off")
                                if adj.after.length_cm:
                                    d3.metric("Length", f"{adj.after.length_cm:g} cm",
                                              delta=f"{adj.after.length_cm - (adj.before.length_cm or 0):+.1f} cm",
                                              delta_color="off")
                                for n in adj.notes:
                                    st.info(n)
                                st.dataframe(pd.DataFrame([{"Change": c.what, "Pattern": c.old, "Yours": c.new}
                                                           for c in adj.changes]), hide_index=True,
                                             use_container_width=True)
                                if st.button("Write my version of the pattern",
                                             help="The LLM rewrites the pattern in its own style; the result is "
                                                  "re-read and checked row by row. If the check fails you get a "
                                                  "version written by code."):
                                    with st.spinner("Rewriting and checking…"):
                                        st.session_state["rewrite"] = rewriter.run(
                                            text, p, adj, use_llm=bool(settings.openrouter_api_key))
                                rw = st.session_state.get("rewrite")
                                if rw is not None:
                                    if rw.method == "code_render":
                                        st.warning("The rewritten text did not pass the check"
                                                   + (f" ({rw.problems[0]})" if rw.problems else "")
                                                   + " — showing a version written by code instead.")
                                    else:
                                        st.success("Rewritten and verified: every row matches the adjusted pattern.")
                                    st.code(rw.text, language=None)

# ---------- Yarn tab (UC3) ----------
with tab_yarn:
    how = st.segmented_control("I know…", ["the yarn's name", "only its fibre and weight"],
                               default="the yarn's name", key="yarn-how") or "the yarn's name"
    yarn_text, fibre, weight = "", "—", "—"
    if how == "the yarn's name":
        yarn_text = st.text_input("Yarn", placeholder="YarnArt Jeans, gazal baby wool, Drops Karisma …",
                                  help="Brands sold in Ukraine; typos and Cyrillic names are fine.")
    else:
        c1, c2 = st.columns(2)
        fibre = c1.selectbox("Fibre", ["—"] + sorted(kb.fibres()))
        weight = c2.selectbox("Weight", ["—", "Lace", "Light Fingering", "Fingering", "Sport", "DK",
                                         "Worsted", "Aran", "Bulky", "Super Bulky"])
    yarn_row = None
    if yarn_text:
        link = yarn_linker.run(yarn_linker.LinkerInput(text=yarn_text))
        if link.status == "match":
            yarn_row = next(y for y in yarn_linker.yarns() if int(y["yarn_id"]) == link.yarn_id)
            st.success(f"Found: **{yarn_linker.display_name(yarn_row['brand'], yarn_row['name'])}** · {yarn_row['weight']} · {yarn_row['fibres']}")
        elif link.status == "ambiguous":
            options = [yarn_linker.display_name(c.brand, c.name) for c in link.candidates]
            pick = st.radio("Several yarns have this name — which one?", options)
            cand = link.candidates[options.index(pick)]
            yarn_row = next(y for y in yarn_linker.yarns() if int(y["yarn_id"]) == cand.yarn_id)
        else:
            st.warning("This yarn is not in our table. Choose the fibre and weight instead."
                       + (f" Closest: {', '.join(yarn_linker.display_name(c.brand, c.name) for c in link.candidates[:2] if c.score > 0.5)}"
                          if any(c.score > 0.5 for c in link.candidates) else ""))
    use_fibre = fibre != "—" and weight != "—"
    if not (yarn_row or use_fibre or yarn_text):
        html('<div class="kc-card"><h3>Which needles for this yarn?</h3>'
             '<p class="kc-sub">Name a yarn, or pick a fibre and weight. Needle sizes and the expected gauge come '
             'from the yarn label and the Craft Yarn Council table; the advisor adds fibre care and tips.</p>'
             + tiles([("🪡", "Needles", "a range in mm and where to start"),
                      ("📐", "Expected gauge", "stitches per 10 cm, flagged when the label looks off"),
                      ("🧼", "Fibre advice", "washing, blocking, warmth and drape"),
                      ("🔎", "Fuzzy names", "typos and Cyrillic brand names are understood")])
             + '<p class="kc-sub" style="margin:0.9rem 0 0.2rem">Try</p>'
             + chips(["YarnArt Jeans", "Gazzal Baby Wool", "DROPS Karisma", "Alize Cotton Gold", "Himalaya Everyday"])
             + "</div>")
    if yarn_row or use_fibre:
        f = yarn_advisor.yarn_facts(yarn_row, None if yarn_row else fibre, None if yarn_row else weight)
        m = st.columns(3)
        m[0].metric("Needles", f"{f.needle_mm[0]:g}–{f.needle_mm[1]:g} mm" if f.needle_mm[0] != f.needle_mm[1]
                    else f"{f.needle_mm[0]:g} mm")
        m[1].metric("Gauge / 10 cm", f"{f.gauge_sts_10cm[0]:g}–{f.gauge_sts_10cm[1]:g} sts"
                    if f.gauge_sts_10cm[0] != f.gauge_sts_10cm[1] else f"{f.gauge_sts_10cm[0]:g} sts")
        m[2].metric("Start with", f"{f.suggested_needle_mm:g} mm")
        if f.warn_gauge:
            st.warning("The label gauge doesn't fit this yarn's weight category — knit a swatch and trust it.")
        cur_pr = current_project()
        if cur_pr is not None and cur_pr.stage == "setup":
            if st.button(f"➕ Use this yarn and {f.suggested_needle_mm:g} mm needles in “{cur_pr.name}”"):
                res = (project.set_yarn(cur_pr, yarn_linker.display_name(yarn_row['brand'], yarn_row['name'])) if yarn_row
                       else project.set_yarn(cur_pr, fibre=fibre, weight=weight))
                project.set_needles(cur_pr, f.suggested_needle_mm)
                db.save(cur_pr)
                st.session_state.pop(f"step-{cur_pr.id}", None)
                (st.success if res.ok else st.warning)(res.message + " Needles set to "
                                                       f"{f.suggested_needle_mm:g} mm. Open My project to continue.")
        st.markdown("**Ask about this yarn**")
        question = st.text_input("Question", value="What needles and gauge should I expect?",
                                 label_visibility="collapsed")
        if st.button("Ask the advisor", type="primary", disabled=not settings.openrouter_api_key):
            with st.spinner("Asking (free models can take up to a minute)…"):
                try:
                    st.session_state["advice"] = yarn_advisor.run(yarn_advisor.AdvisorInput(
                        yarn_id=int(yarn_row["yarn_id"]) if yarn_row else None,
                        fibre=None if yarn_row else fibre, weight=None if yarn_row else weight, question=question))
                except (RuntimeError, ValueError) as e:
                    st.error(f"Could not get advice: {e}")
        adv = st.session_state.get("advice")
        if adv is not None and adv.status == "answered":
            if adv.violations:
                st.warning("Some details could not be verified: " + "; ".join(adv.violations[:3]))
            st.markdown(adv.answer)
        with st.expander("Facts used (computed by code from the yarn label, CYC table and fibre KB)"):
            st.code(f.as_text(), language=None)


# ---------- My project tab (UC5: setup → lock → knitting) ----------
STEPS = ["pattern", "yarn", "gauge", "generate"]
STEP_NAMES = {"pattern": "Pattern & size", "yarn": "Yarn & needles", "gauge": "Your gauge", "generate": "Generate"}
STEP_SHORT = {"pattern": "1 · Pattern", "yarn": "2 · Needles", "gauge": "3 · Gauge", "generate": "4 · Generate"}


def step_done(pr: project.Project, step: str) -> bool:
    need = project.missing(pr)
    return {"pattern": pr.pattern is not None and "size" not in need, "yarn": pr.needle_mm is not None,
            "gauge": pr.gauge_sts_10cm is not None, "generate": pr.stage == "knitting"}[step]


def go_to(pr: project.Project, step: str) -> None:
    st.session_state[f"step-{pr.id}"] = step
    st.rerun()


def next_open_step(pr: project.Project) -> str:
    return next((s_ for s_ in STEPS[:3] if not step_done(pr, s_)), "generate")


def notify(result) -> None:
    st.session_state["flash"] = ("ok" if result.ok else "warn", result.message)


def render_chat(pr: project.Project, height: int = 430) -> None:
    hist = st.session_state.setdefault(f"chat-{pr.id}", [])
    box = st.container(height=height, border=False)
    with box:
        if not hist and pr.stage == "knitting":
            st.caption("Ask about the row you're on, a stitch, or tell me where you are:")
            html(chips(["I finished row 12", "what does ssk mean?", "explain this round", "show me the chart",
                        "I ripped back 2 rows"]))
        elif not hist:
            st.caption("Ask anything about your pattern, yarn or a stitch — or set up the project by chat:")
            html(chips(["I'm using YarnArt Jeans on 4 mm needles", "my swatch is 22 sts and 30 rows over 10 cm",
                        "I want size M", "what does ssk mean?", "show me the chart"]))
        for m in hist[-12:]:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])
                if m.get("chart"):
                    st.image(m["chart"])
                if m.get("trace"):
                    with st.expander("LLM trace"):
                        for rec in m["trace"]:
                            st.markdown(f"**node `{rec['node']}`** · {rec['latency_s']} s"
                                        + (f" · error: {rec['error']}" if rec.get("error") else ""))
                            for c in rec.get("llm_calls") or []:
                                st.markdown(f"- model call `{c['model']}` · "
                                            + ("cached" if c["cached"] else f"{c['latency_s']} s")
                                            + (f" · {c['tokens']} tokens" if c.get("tokens") else "")
                                            + (f" · tool calls: {', '.join(c['tool_calls'])}" if c["tool_calls"] else ""))
                            if not rec.get("llm_calls"):
                                st.caption("no model call (code only)")
                            st.json(rec.get("output"), expanded=False)
    msg = st.chat_input("Message Knitting Copilot…", key=f"chat-in-{pr.id}")
    if msg:
        with st.spinner("Thinking…"):
            n_before = len(get_trace(pr.id))
            try:
                out = chat_graph.chat(pr.id, msg)
                reply, show = out["reply"], out.get("show")
                reply += f"\n\n_routed to {out['intent']} ({out['route_method']})_"
            except (RuntimeError, ValueError) as e:
                reply, show = f"Sorry, that did not work: {e}", ""
        entry = {"role": "assistant", "content": reply, "trace": get_trace(pr.id)[n_before:]}
        if show == "chart":
            pr2 = db.load(pr.id)
            pat = pr2.working.pattern if pr2.stage == "knitting" and pr2.working else pr2.pattern
            if pat is not None:
                entry["chart"] = charts.render_png(charts.build(pat, None if pr2.stage == "knitting" else pr2.size))
        hist += [{"role": "user", "content": msg}, entry]
        st.session_state.pop(f"step-{pr.id}", None)          # the chat may have filled a step: jump to the next one
        st.rerun()


def step_pattern(pr: project.Project) -> None:
    if pr.pattern is not None:
        sim = simulate(pr.pattern, pr.size if pr.size in (pr.pattern.sizes or []) else None)
        html(f'<div class="kc-summary"><b>{pr.pattern.title or "Your pattern"}</b><span>'
             f'{"in the round" if pr.pattern.construction == "round" else "knitted flat"} · cast on {sim.cast_on}'
             f' · {len(sim.rows)} rows' + (f' · sizes {", ".join(pr.pattern.sizes)}' if pr.pattern.sizes else "")
             + "</span></div>")
        if pr.pattern.sizes:
            sel = st.segmented_control("Which size are you knitting?", pr.pattern.sizes,
                                       default=pr.size if pr.size in pr.pattern.sizes else None, key=f"size-{pr.id}")
            if sel and sel != pr.size:
                notify(project.select_size(pr, sel)); db.save(pr); st.rerun()
        with st.expander("Use a different pattern"):
            _pattern_input(pr)
    else:
        st.caption("Paste the written instructions (cast on, rows/rounds, bind off). Sizes like “S (M, L)” are fine.")
        _pattern_input(pr)


def _pattern_input(pr: project.Project) -> None:
    examples = example_patterns()
    src = st.radio("Source", ["Paste text", "Use an example"] + (["From Pattern explorer"] if st.session_state.get(
        "explorer_text") else []), horizontal=True, label_visibility="collapsed", key=f"src-{pr.id}")
    if src == "Use an example":
        ex = st.selectbox("Example", list(examples), key=f"ex-{pr.id}")
        text = examples[ex]["text"]
        st.code(text, language=None)
    elif src == "From Pattern explorer":
        text = st.session_state["explorer_text"]
        st.code(text[:600] + ("…" if len(text) > 600 else ""), language=None)
    else:
        text = st.text_area("Pattern text", value=pr.pattern_text or "", height=220, key=f"ptext-{pr.id}",
                            placeholder="CO 88 (96) sts. Join to work in the round.\nRnd 1: *k2, p2; rep from * to end.\n…",
                            label_visibility="collapsed")
    if st.button("Read pattern", type="primary", disabled=not (text or "").strip(), key=f"read-{pr.id}"):
        with st.spinner("Reading the pattern…"):
            res = project.set_pattern(pr, text)
        notify(res); db.save(pr)
        st.rerun()


def step_yarn(pr: project.Project) -> None:
    st.caption("Yarn is optional — it gives you a needle suggestion and fibre advice. Needles are required.")
    y_col, b_col = st.columns([3, 1], vertical_alignment="bottom")
    ytext = y_col.text_input("Yarn", value=(pr.yarn.label or pr.yarn.text or "") if pr.yarn else "",
                             placeholder="e.g. YarnArt Jeans, Gazzal Baby Wool",
                             key=f"yarn-{pr.id}-{pr.yarn.label if pr.yarn else ''}")
    if b_col.button("Find yarn", use_container_width=True, disabled=not ytext.strip(), key=f"fy-{pr.id}"):
        res = project.set_yarn(pr, ytext)
        st.session_state[f"yarn-cands-{pr.id}"] = res.data.get("candidates")
        notify(res); db.save(pr); st.rerun()
    cands = st.session_state.get(f"yarn-cands-{pr.id}")
    if cands:
        pick = st.radio("Several yarns have this name — which one?", cands, key=f"yc-{pr.id}")
        if st.button("Use this yarn", key=f"ycu-{pr.id}"):
            st.session_state.pop(f"yarn-cands-{pr.id}")
            notify(project.set_yarn(pr, pick)); db.save(pr); st.rerun()
    suggested, why = None, ""
    if pr.yarn and pr.yarn.yarn_id:
        row = next((y for y in yarn_linker.yarns() if int(y["yarn_id"]) == pr.yarn.yarn_id), None)
        if row:
            f = yarn_advisor.yarn_facts(row)
            suggested = f.suggested_needle_mm
            if f.main_fibre and not (f.needle_mm[0] <= suggested <= f.needle_mm[1]):
                why = f" (a size off the label because {f.main_fibre} knits {'looser' if suggested < f.needle_mm[0] else 'tighter'})"
            html(f'<div class="kc-summary"><b>🧶 {yarn_linker.display_name(row["brand"], row["name"])}</b><span>{row["weight"]} · '
                 f'{row["fibres"]} · label needles {rng(*f.needle_mm, "mm")} · '
                 f'{rng(*f.gauge_sts_10cm, "sts")} / 10 cm</span></div>')
    n_col, u_col = st.columns([2, 1], vertical_alignment="bottom")
    unit = u_col.segmented_control("Size system", ["mm", "US"], default="mm", key=f"nu-{pr.id}") or "mm"
    needle = n_col.number_input("Needle size" + (" (mm)" if unit == "mm" else " (US)"),
                                min_value=0.5, max_value=25.0, step=0.25 if unit == "mm" else 1.0,
                                value=pr.needle_mm if unit == "mm" else None, placeholder="e.g. 4",
                                key=f"needle-{pr.id}-{unit}")
    if pr.pattern and pr.pattern.gauge and pr.pattern.gauge.needle_mm:
        st.caption(f"The pattern suggests {pr.pattern.gauge.needle_mm:g} mm"
                   + (f"; for your yarn start with {suggested:g} mm{why}." if suggested else "."))
    quick, source = suggested, "your yarn"
    if quick is None and pr.pattern and pr.pattern.gauge and pr.pattern.gauge.needle_mm:
        quick, source = pr.pattern.gauge.needle_mm, "the pattern"
    c1, c2 = st.columns(2)
    if c1.button("Save needles and continue →", type="primary", disabled=needle is None, key=f"ns-{pr.id}",
                 use_container_width=True):
        notify(project.set_needles(pr, needle, "mm" if unit == "mm" else "us")); db.save(pr)
        go_to(pr, next_open_step(pr))
    if quick and c2.button(f"Use {quick:g} mm (from {source})", key=f"nsug-{pr.id}", use_container_width=True):
        notify(project.set_needles(pr, quick)); db.save(pr)
        go_to(pr, next_open_step(pr))


def step_gauge(pr: project.Project) -> None:
    pg = pr.pattern.gauge if pr.pattern else None
    if pg:
        html(f'<div class="kc-summary"><b>Pattern gauge</b><span>{pg.sts_per_10cm:g} sts'
             + (f" × {pg.rows_per_10cm:g} rows" if pg.rows_per_10cm else "") + " per 10 cm"
             + (f" on {pg.needle_mm:g} mm" if pg.needle_mm else "") + "</span></div>")
    st.caption("Knit a swatch of about 15 × 15 cm, wash and dry it, then count the stitches and rows across 10 cm.")
    g1, g2 = st.columns(2)
    sts = g1.number_input("Stitches per 10 cm", min_value=1.0, max_value=60.0, step=0.5,
                          value=pr.gauge_sts_10cm, placeholder="e.g. 22", key=f"gs-{pr.id}")
    rows = g2.number_input("Rows per 10 cm (optional)", min_value=1.0, max_value=80.0, step=0.5,
                           value=pr.gauge_rows_10cm, placeholder="e.g. 30", key=f"gr-{pr.id}",
                           help="Needed when the pattern says “work until it measures …”.")
    c1, c2 = st.columns(2)
    if c1.button("Save gauge and continue →", type="primary", disabled=sts is None, key=f"gsave-{pr.id}",
                 use_container_width=True):
        notify(project.set_gauge(pr, sts, rows)); db.save(pr)
        go_to(pr, next_open_step(pr))
    if pg and c2.button("My gauge matches the pattern", key=f"gsame-{pr.id}", use_container_width=True):
        notify(project.set_gauge(pr, pg.sts_per_10cm, pg.rows_per_10cm)); db.save(pr)
        go_to(pr, next_open_step(pr))


def step_generate(pr: project.Project) -> None:
    need = project.missing(pr)
    if need:
        st.info("Still needed: " + ", ".join(need) + ".")
        cols = st.columns(len(need))
        for c, n_ in zip(cols, need):
            target = {"pattern": "pattern", "size": "pattern", "needles": "yarn", "gauge": "gauge"}[n_]
            if c.button(f"Set {n_}", key=f"jump-{n_}-{pr.id}", use_container_width=True):
                go_to(pr, target)
        return
    adj = gauge.adjust(pr.pattern, pr.size, gauge.KnitterGauge(
        sts_per_10cm=pr.gauge_sts_10cm, rows_per_10cm=pr.gauge_rows_10cm, needle_mm=pr.needle_mm))
    if not adj.ok:
        st.error(" ".join(adj.notes))
        return
    st.markdown("**Preview of your working pattern**")
    d1, d2, d3 = st.columns(3)
    d1.metric("Cast on", adj.chosen_stitches, delta=adj.chosen_stitches - adj.changes[0].old)
    d2.metric("Width", f"{adj.after.width_cm:g} cm", delta=f"{adj.after.width_cm - adj.before.width_cm:+.1f} cm",
              delta_color="off")
    if adj.after.length_cm:
        d3.metric("Length", f"{adj.after.length_cm:g} cm",
                  delta=f"{adj.after.length_cm - (adj.before.length_cm or 0):+.1f} cm", delta_color="off")
    for n_ in adj.notes:
        st.caption("ℹ️ " + n_)
    with st.expander(f"All {len(adj.changes)} changes"):
        st.dataframe(pd.DataFrame([{"Change": c.what, "Pattern": c.old, "Yours": c.new} for c in adj.changes]),
                     hide_index=True, use_container_width=True)
    st.caption("Generating locks the setup so the row counter stays valid. You can start over later.")
    if st.button("🧶 Generate and start knitting", type="primary", use_container_width=True, key=f"gen-{pr.id}"):
        notify(project.generate_working_pattern(pr)); db.save(pr); st.rerun()


def setup_view(pr: project.Project) -> None:
    current = st.session_state.get(f"step-{pr.id}") or next_open_step(pr)
    main, side = st.columns([3, 2], gap="large")
    with main:
        nav = st.columns(4)
        for c, s_ in zip(nav, STEPS):
            label = ("✓ " + STEP_SHORT[s_].split(" · ")[1]) if step_done(pr, s_) else STEP_SHORT[s_]
            if c.button(label, key=f"nav-{s_}-{pr.id}", use_container_width=True,
                        type="primary" if s_ == current else "secondary"):
                go_to(pr, s_)
        with st.container(border=True):
            st.markdown(f"#### {STEP_NAMES[current]}")
            {"pattern": step_pattern, "yarn": step_yarn, "gauge": step_gauge, "generate": step_generate}[current](pr)
            if current == "pattern" and step_done(pr, "pattern"):
                if st.button("Continue →", type="primary", key=f"cont-{pr.id}"):
                    go_to(pr, next_open_step(pr))
    with side:
        with st.container(border=True):
            st.markdown("#### 💬 Or just tell me")
            render_chat(pr, height=380)


def knitting_view(pr: project.Project) -> None:
    v = tracker.view(pr)
    unit = "Round" if v.side == "round" else "Row"
    main, side = st.columns([3, 2], gap="large")
    with main:
        with st.container(border=True):
            st.progress(v.percent / 100, text=f"{unit} {v.number} of {v.total} · {v.percent}% done")
            html(f'<div class="kc-now-row"><span class="kc-label">{v.label}'
                 + (f" · {v.time_of}" if v.time_of else "") + (f" · {v.side}" if v.side in ("RS", "WS") else "")
                 + f'</span><div class="kc-instr">{v.instruction}</div>'
                 f'<span class="kc-counts">{v.start_count} → <b>{v.end_count}</b> stitches'
                 + (f" · pattern says {v.stated_count}" if v.stated_count is not None else "")
                 + f" · {v.rows_left} {unit.lower()}{'' if v.rows_left == 1 else 's'} left</span></div>")
            b1, b2 = st.columns([1, 2])
            if b1.button("◀ Back", use_container_width=True, disabled=v.index == 0):
                tracker.prev_row(pr); db.save(pr); st.rerun()
            if b2.button(f"Done — next {unit.lower()} ▶", type="primary", use_container_width=True,
                         disabled=v.rows_left == 0):
                tracker.next_row(pr); db.save(pr); st.rerun()
            with st.popover(f"Jump to a {unit.lower()}"):
                n_ = st.number_input(f"{unit} number", 1, v.total, v.number, key=f"jump-{pr.id}")
                if st.button("Go", key=f"jgo-{pr.id}"):
                    tracker.goto(pr, int(n_) - 1); db.save(pr); st.rerun()
        pat = pr.working.pattern
        with st.expander("📜 Working pattern (adjusted to your gauge)"):
            sim = simulate(pat, None)
            st.dataframe(pd.DataFrame([{"Rows": ln.rows, "What to knit": ln.worked_as, "Stitches": ln.stitches,
                                        "Pattern row": ln.instruction}
                                       for ln in row_lines(pat, sim, grouped=True)]),
                         hide_index=True, use_container_width=True,
                         column_config={"What to knit": st.column_config.TextColumn(width="large")})
        with st.expander("🟥 Chart"):
            st.image(charts.render_png(charts.build(pat, None)))
        with st.expander("🔒 Setup (locked) · start over"):
            st.markdown(f"Pattern **{pr.pattern.title or '—'}**" + (f", size **{pr.size}**" if pr.size else "")
                        + f" · needles **{pr.needle_mm:g} mm** · gauge **{pr.gauge_sts_10cm:g} sts**"
                        + (f" × {pr.gauge_rows_10cm:g} rows" if pr.gauge_rows_10cm else "") + " / 10 cm"
                        + (f" · yarn **{pr.yarn.label or pr.yarn.text}**" if pr.yarn else ""))
            if pr.history:
                st.caption("History: " + " · ".join(pr.history[-3:]))
            confirm = st.checkbox("I understand my row progress will be reset", key=f"so-{pr.id}")
            if st.button("Start over from setup (new version)", disabled=not confirm, key=f"sob-{pr.id}"):
                notify(project.start_over(pr)); db.save(pr)
                st.session_state.pop(f"step-{pr.id}", None); st.rerun()
    with side:
        with st.container(border=True):
            st.markdown("#### 💬 Ask while you knit")
            render_chat(pr, height=420)


with tab_project:
    projects = db.list_projects()
    # fixed order (by name, then creation) so saving a project never moves the selection
    ids = sorted((pid for pid, _, _ in projects), key=lambda i: (dict((a, b) for a, b, _ in projects)[i].lower(), i))
    names = {pid: name for pid, name, _ in projects}
    dup = {n for n in names.values() if list(names.values()).count(n) > 1}
    label = {i: names[i] + (f"  ·  #{[j for j in ids if names[j] == names[i]].index(i) + 1}" if names[i] in dup
                            else "") for i in ids}
    if (pending := st.session_state.pop("pending_project", None)) in ids:
        st.session_state["project_pick"] = pending
    if st.session_state.get("project_pick") not in ids and ids:
        st.session_state["project_pick"] = st.session_state.get("project_id") if st.session_state.get(
            "project_id") in ids else ids[0]
    top_l, top_r = st.columns([3, 1], vertical_alignment="bottom")
    if projects:
        cur = top_l.selectbox("Project", ids, format_func=lambda i: label[i], key="project_pick")
        st.session_state["project_id"] = cur
    with top_r.popover("＋ New project", use_container_width=True):
        nm = st.text_input("Project name", placeholder="e.g. Red beanie", key="new-name")
        if nm.strip() in names.values():
            st.caption("You already have a project with this name.")
        if st.button("Create", type="primary", disabled=not nm.strip(), key="new-create"):
            pr = project.new_project(nm.strip()); db.save(pr)
            st.session_state["pending_project"] = pr.id
            st.rerun()
    flash = st.session_state.pop("flash", None)
    if flash:
        (st.success if flash[0] == "ok" else st.warning)(flash[1])
    if not projects:
        html('<div class="kc-card"><h3>Start your first project</h3>'
             '<p class="kc-sub">Press <b>＋ New project</b> above. Setup takes four short steps; once you generate '
             'the working pattern it is locked so your row count stays valid.</p><div class="kc-steps">'
             '<div class="kc-step"><span class="kc-num">1</span><h4>Pattern & size</h4>'
             '<p>Paste the pattern or use an example.</p></div>'
             '<div class="kc-step"><span class="kc-num">2</span><h4>Yarn, needles, gauge</h4>'
             '<p>Your yarn and swatch — by form or by chat.</p></div>'
             '<div class="kc-step"><span class="kc-num">3</span><h4>Generate & knit</h4>'
             '<p>Preview the changes, lock, and follow the row tracker.</p></div></div></div>')
        st.stop()
    pr = db.load(cur)
    if pr.stage == "knitting":
        knitting_view(pr)
    else:
        setup_view(pr)
