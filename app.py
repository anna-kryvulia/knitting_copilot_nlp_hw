"""Knitting Copilot — Streamlit UI.

Phase 4 (in progress): Pattern tab (paste → parse → row-by-row simulation) and abbreviation lookup.
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
tab_project, tab_pattern, tab_yarn = st.tabs(["My project", "Pattern explorer", "Yarn"])

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
            st.session_state["adjustment"] = None
            st.session_state["rewrite"] = None
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
    st.caption("Type a yarn name (brands sold in Ukraine) — or describe the fibre and weight.")
    c1, c2 = st.columns([3, 2])
    with c1:
        yarn_text = st.text_input("Yarn", placeholder="YarnArt Jeans, gazal baby wool, Drops Karisma …")
        question = st.text_input("Question", value="What needles and gauge should I expect?")
    with c2:
        fibre = st.selectbox("…or fibre", ["—"] + sorted(kb.fibres()))
        weight = st.selectbox("…and weight", ["—", "Lace", "Light Fingering", "Fingering", "Sport", "DK",
                                              "Worsted", "Aran", "Bulky", "Super Bulky"])
    yarn_row = None
    if yarn_text:
        link = yarn_linker.run(yarn_linker.LinkerInput(text=yarn_text))
        if link.status == "match":
            yarn_row = next(y for y in yarn_linker.yarns() if int(y["yarn_id"]) == link.yarn_id)
            st.success(f"Found: **{yarn_row['brand']} {yarn_row['name']}** · {yarn_row['weight']} · {yarn_row['fibres']}")
        elif link.status == "ambiguous":
            options = [f"{c.brand} {c.name}" for c in link.candidates]
            pick = st.radio("Several yarns have this name — which one?", options)
            cand = link.candidates[options.index(pick)]
            yarn_row = next(y for y in yarn_linker.yarns() if int(y["yarn_id"]) == cand.yarn_id)
        else:
            st.warning("This yarn is not in our table. Choose the fibre and weight instead."
                       + (f" Closest: {', '.join(c.brand + ' ' + c.name for c in link.candidates[:2] if c.score > 0.5)}"
                          if any(c.score > 0.5 for c in link.candidates) else ""))
    use_fibre = fibre != "—" and weight != "—"
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
with tab_project:
    projects = db.list_projects()
    left_col, right_col = st.columns([1, 2])
    with left_col:
        names = {pid: f"{name} ({updated[:10]})" for pid, name, updated in projects}
        choice = st.selectbox("Project", ["+ New project"] + list(names), format_func=lambda x: names.get(x, x))
        if choice == "+ New project":
            new_name = st.text_input("Name", value="My project")
            if st.button("Create project"):
                pr = project.new_project(new_name)
                db.save(pr)
                st.rerun()
            st.stop()
        pr = db.load(choice)

        def apply(result):
            db.save(pr)
            (st.success if result.ok else st.warning)(result.message)

        st.caption(f"Stage: **{pr.stage}** · version {pr.version}")
        locked = pr.stage == "knitting"
        with st.expander("Setup", expanded=not locked):
            need = project.missing(pr)
            st.markdown(" · ".join(("⬜ " if f in need else "✅ ") + f for f in ["pattern", "size", "gauge", "needles"])
                        + f" · {'✅' if pr.yarn else '◻️'} yarn (optional)")
            y = st.text_input("Yarn", value=(pr.yarn.label or pr.yarn.text or "") if pr.yarn else "", disabled=locked)
            if st.button("Set yarn", disabled=locked or not y):
                apply(project.set_yarn(pr, y))
            c1, c2, c3 = st.columns(3)
            n = c1.number_input("Needles (mm)", 1.0, 25.0, value=pr.needle_mm or 4.0, step=0.25, disabled=locked)
            gs = c2.number_input("sts / 10 cm", 1.0, 60.0, value=pr.gauge_sts_10cm or 20.0, step=0.5, disabled=locked)
            gr = c3.number_input("rows / 10 cm", 0.0, 80.0, value=pr.gauge_rows_10cm or 0.0, step=0.5, disabled=locked,
                                 help="0 = not measured")
            if st.button("Save needles and gauge", disabled=locked):
                project.set_needles(pr, n)
                apply(project.set_gauge(pr, gs, gr or None))
            text = st.text_area("Pattern text", value=pr.pattern_text or "", height=160, disabled=locked)
            if st.button("Read pattern into project", disabled=locked or not text.strip()):
                with st.spinner("Reading the pattern…"):
                    apply(project.set_pattern(pr, text))
            if pr.pattern and pr.pattern.sizes:
                sz = st.selectbox("Size", pr.pattern.sizes, disabled=locked,
                                  index=pr.pattern.sizes.index(pr.size) if pr.size in pr.pattern.sizes else 0)
                if st.button("Choose size", disabled=locked):
                    apply(project.select_size(pr, sz))
        if not locked:
            if st.button("Generate working pattern", type="primary", disabled=bool(project.missing(pr))):
                apply(project.generate_working_pattern(pr))
                st.rerun()
        else:
            confirm = st.checkbox("I understand my progress will be reset")
            if st.button("Start over from setup", disabled=not confirm):
                apply(project.start_over(pr))
                st.rerun()
        if pr.history:
            st.caption("History: " + " · ".join(pr.history[-3:]))

    with right_col:
        if pr.stage == "knitting":
            v = tracker.view(pr)
            st.progress(v.percent / 100, text=f"{'Round' if v.side == 'round' else 'Row'} {v.number} of {v.total}"
                                              + (f" · {v.label} ({v.time_of})" if v.time_of else f" · {v.label}"))
            st.markdown(f"#### {v.instruction}")
            st.caption(f"Stitches {v.start_count} → **{v.end_count}**"
                       + (f" · the pattern says {v.stated_count}" if v.stated_count is not None else "")
                       + f" · {v.rows_left} row{'' if v.rows_left == 1 else 's'} left")
            b1, b2, _ = st.columns([1, 1, 3])
            if b1.button("◀ Previous row"):
                tracker.prev_row(pr); db.save(pr); st.rerun()
            if b2.button("Next row ▶", type="primary"):
                tracker.next_row(pr); db.save(pr); st.rerun()
        st.divider()
        hist = st.session_state.setdefault(f"chat-{pr.id}", [])
        for m in hist[-12:]:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])
                if m.get("chart"):
                    st.image(m["chart"])
        msg = st.chat_input("Ask about your pattern, yarn or stitches — or tell me your yarn, needles and gauge")
        if msg:
            with st.spinner("Thinking…"):
                try:
                    out = chat_graph.chat(pr.id, msg)
                    reply, show = out["reply"], out.get("show")
                    reply += f"\n\n_routed to {out['intent']} ({out['route_method']})_"
                except (RuntimeError, ValueError) as e:
                    reply, show = f"Sorry, that did not work: {e}", ""
            entry = {"role": "assistant", "content": reply}
            if show == "chart":
                pr2 = db.load(pr.id)
                pat = pr2.working.pattern if pr2.stage == "knitting" and pr2.working else pr2.pattern
                entry["chart"] = charts.render_png(charts.build(pat, None if pr2.stage == "knitting" else pr2.size))
            hist += [{"role": "user", "content": msg}, entry]
            st.rerun()
