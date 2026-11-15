"""Yarn advisor (UC3): yarn (linked name, or fibre + weight) + question → grounded advice.

Purpose: tell the knitter which needles and gauge to expect and how the fibre behaves, using only data
from data/yarns.csv, the CYC weight table and the fibre KB.
Input: AdvisorInput(yarn_text | fibre + weight, question). Output: AdvisorOutput(answer, facts, status...).
Model calls: yes (prompts/yarn_advisor.md), up to 1 + MAX_REPAIRS. Tool calls: yarn_linker (code).

Code computes every number (yarn_facts); the LLM only phrases the answer; the same number/citation check as
the explainer rejects anything not in the facts.
"""

from __future__ import annotations

import re
import time

from pydantic import BaseModel

from knit_copilot import kb, llm
from knit_copilot.components import yarn_linker

MAX_REPAIRS = 1
CITATION = re.compile(r"\[([a-z]+:[a-z0-9_ ]+)\]")


class YarnFacts(BaseModel):
    title: str
    lines: list[str]
    citations: list[str]
    numbers: set[float]
    cyc_category: int
    needle_mm: tuple[float, float]
    suggested_needle_mm: float
    gauge_sts_10cm: tuple[float, float]
    warn_gauge: bool
    main_fibre: str | None

    def as_text(self) -> str:
        return "\n".join([self.title] + [f"- {x}" for x in self.lines]
                         + ["Allowed citations: " + ", ".join(f"[{c}]" for c in self.citations)])


def _round_needle(mm: float) -> float:
    sizes = kb.yarn_weights()["standard_needles_mm"]
    return min(sizes, key=lambda s: (abs(s - mm), s))


def _category_by_ravelry(weight: str) -> dict:
    for c in kb.yarn_weights()["categories"]:
        if weight.lower() in [n.lower() for n in c["ravelry_names"]] or weight.lower() == c["name"].lower():
            return c
    raise KeyError(f"unknown yarn weight {weight!r}")


def yarn_facts(row: dict | None = None, fibre: str | None = None, weight: str | None = None) -> YarnFacts:
    """Facts for a yarn row from yarns.csv, or for a fibre + weight description."""
    if row is not None:
        cat = next(c for c in kb.yarn_weights()["categories"] if c["id"] == int(row["cyc_category"]))
        fibre = row["main_fibre"] or None
        needle = (float(row["needle_min_mm"]), float(row["needle_max_mm"]))
        gauge = (float(row["gauge_min_sts_10cm"]), float(row["gauge_max_sts_10cm"]))
        needle_src = "the yarn label" if row["needle_source"] == "label" else f"the CYC range for {cat['name']} yarn"
        gauge_src = "the yarn label" if row["gauge_source"] == "label" else f"the CYC range for {cat['name']} yarn"
        warn = bool(row["gauge_flag"])
        title = f"YARN: {row['brand']} {row['name']}"
        lines = [f"Weight: {row['weight']} = CYC category {cat['id']} ({cat['name']}).",
                 f"Fibres: {row['fibres']}.",
                 f"Ball: {row['grams']} g, {row['length_m']} m." if row["grams"] and row["length_m"] else "",
                 f"Machine washable according to the label: {'yes' if row['machine_washable'] == 'True' else 'no / not stated'}."]
        cites = [f"yarn:{row['yarn_id']}", f"cyc:{cat['id']}"]
    else:
        cat = _category_by_ravelry(weight or "")
        needle, gauge = tuple(cat["needle_mm"]), tuple(cat["sts_per_10cm"])
        needle_src = gauge_src = f"the CYC range for {cat['name']} yarn"
        warn = False
        title = f"YARN: {fibre} yarn, {weight} weight (no specific yarn)"
        lines = [f"Weight: {weight} = CYC category {cat['id']} ({cat['name']})."]
        cites = [f"cyc:{cat['id']}"]

    fk = kb.fibres().get(fibre) if fibre else None
    mid = _round_needle((needle[0] + needle[1]) / 2)
    adjust = fk["needle_adjust_mm"] if fk else 0
    suggested = _round_needle(mid + adjust) if adjust else mid
    lines += [f"Needle size: {needle[0]:g}–{needle[1]:g} mm (from {needle_src})." if needle[0] != needle[1]
              else f"Needle size: {needle[0]:g} mm (from {needle_src}).",
              f"Expected gauge: {gauge[0]:g}–{gauge[1]:g} stitches per 10 cm (from {gauge_src})." if gauge[0] != gauge[1]
              else f"Expected gauge: {gauge[0]:g} stitches per 10 cm (from {gauge_src}).",
              f"CYC guideline for this weight: {cat['sts_per_10cm'][0]}–{cat['sts_per_10cm'][1]} stitches per 10 cm on "
              f"{cat['needle_mm'][0]:g}–{cat['needle_mm'][1]:g} mm needles."]
    if cat.get("note"):
        lines.append(f"CYC note: {cat['note']}")
    if adjust:
        lines.append(f"Suggested starting needle: {suggested:g} mm ({'down' if adjust < 0 else 'up'} from {mid:g} mm "
                     f"because of the fibre).")
    else:
        lines.append(f"Suggested starting needle: {suggested:g} mm.")
    if warn:
        lines.append("WARNING: the label gauge does not fit the yarn's weight category (data problem); the knitter "
                     "should knit a swatch and trust the swatch, not the label.")
    if fk:
        lines += [f"Fibre {fibre}: elasticity {fk['elasticity']}, warmth {fk['warmth']}, drape {fk['drape']}.",
                  f"Good for: {', '.join(fk['good_for']) or '—'}. Less suited for: {', '.join(fk['avoid_for']) or '—'}.",
                  f"Care: {fk['care']}", f"Blocking: {fk['blocking']}"] + [f"Tip: {t}" for t in fk["tips"]]
        cites.append(f"fibre:{fibre}")
    lines = [x for x in lines if x]
    text = " ".join(lines)
    numbers = {float(x) for x in re.findall(r"\d+(?:\.\d+)?", text)} | {1, 2, 3, 10}
    return YarnFacts(title=title, lines=lines, citations=cites, numbers=numbers, cyc_category=cat["id"],
                     needle_mm=needle, suggested_needle_mm=suggested, gauge_sts_10cm=gauge, warn_gauge=warn,
                     main_fibre=fibre)


class AdvisorInput(BaseModel):
    yarn_text: str | None = None          # free text, linked with the yarn linker
    yarn_id: int | None = None            # already linked
    fibre: str | None = None
    weight: str | None = None
    question: str = "What needles and gauge should I expect, and what should I know about this yarn?"
    time_budget_s: float = 90


class AdvisorOutput(BaseModel):
    status: str                            # answered | ambiguous | unknown_yarn
    answer: str = ""
    facts: str = ""
    candidates: list[str] = []
    citations: list[str] = []
    violations: list[str] = []
    attempts: int = 0
    yarn_id: int | None = None


def check(text: str, f: YarnFacts) -> list[str]:
    problems = [f"citation [{c}] is not allowed" for c in dict.fromkeys(CITATION.findall(text)) if c not in f.citations]
    plain = CITATION.sub(" ", text)
    plain = re.sub(r"\b[a-z]+\d+[a-z0-9]*\b|\b\d+/\d+\b", " ", plain, flags=re.I)
    for n in dict.fromkeys(re.findall(r"(?<![\w.])\d+(?:\.\d+)?(?![\w])", plain)):
        if float(n) not in f.numbers:
            problems.append(f"number {n} is not in the yarn facts")
    return problems


def run(inp: AdvisorInput) -> AdvisorOutput:
    row = None
    if inp.yarn_id is not None:
        row = next(y for y in yarn_linker.yarns() if int(y["yarn_id"]) == inp.yarn_id)
    elif inp.yarn_text:
        link = yarn_linker.run(yarn_linker.LinkerInput(text=inp.yarn_text))
        if link.status == "ambiguous":
            return AdvisorOutput(status="ambiguous", candidates=[f"{c.brand} {c.name}" for c in link.candidates])
        if link.status == "none" and not inp.weight:
            return AdvisorOutput(status="unknown_yarn",
                                 candidates=[f"{c.brand} {c.name}" for c in link.candidates if c.score > 0.5])
        if link.status == "match":
            row = next(y for y in yarn_linker.yarns() if int(y["yarn_id"]) == link.yarn_id)
    f = yarn_facts(row, inp.fibre, inp.weight)
    deadline = time.monotonic() + inp.time_budget_s
    feedback, answer, problems, attempts = "", "", [], 0
    for _ in range(1 + MAX_REPAIRS):
        attempts += 1
        msgs = llm.render("yarn_advisor", facts=f.as_text(), question=inp.question, feedback=feedback)
        answer = (llm.chat(msgs, max_tokens=3000, temperature=0.2, deadline=deadline)["content"] or "").strip()
        problems = check(answer, f)
        if not problems:
            break
        feedback = "\nYOUR PREVIOUS ANSWER HAD PROBLEMS — fix them:\n- " + "\n- ".join(problems[:10])
    if f.warn_gauge and not re.search(r"swatch", answer, re.I):     # a code fact: guaranteed, not left to the model
        answer += ("\n\n**Knit a swatch first:** the gauge on this yarn's label does not fit its weight category, "
                   "so measure your own gauge and trust it.")
    return AdvisorOutput(status="answered", answer=answer, facts=f.as_text(),
                         citations=list(dict.fromkeys(CITATION.findall(answer))), violations=problems,
                         attempts=attempts, yarn_id=int(row["yarn_id"]) if row else None)
