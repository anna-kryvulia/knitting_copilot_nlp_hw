"""Build the hand-written eval sets: data/eval/src/*.yaml → validated JSONL with dev/test splits.

Purpose: turn human-readable sources into eval files, checking every label against the real data so a
typo becomes a build error instead of a wrong gold label:
- intents use the label set of docs/CONVENTIONS.md;
- setup tool calls use known tools and arguments, sizes exist; expected project state is computed by code;
- KB ids exist; yarns given as [brand, name] resolve to exactly one row of data/yarns.csv;
- yarn-advice gold numbers come from yarns.csv / yarn_weights.yaml; `must_mention` facts must exist in the KB;
  `warn_gauge` must agree with the Q9 flag in yarns.csv.
Also writes a 20% random review sample for the human check (docs/data/eval_review_sample.md).

Run: python -m knit_copilot.data.build_eval_sets
"""

import csv
import json
import random
from collections import Counter, defaultdict

import yaml

from knit_copilot import kb, units
from knit_copilot.config import ROOT

SRC = ROOT / "data" / "eval" / "src"
OUT = ROOT / "data" / "eval"
SEED = 11

INTENTS = ["setup", "adjust_pattern", "explain", "yarn_advice", "abbreviation_lookup", "knitting_question",
           "chart", "tracker", "validate", "out_of_scope", "smalltalk"]
TOOLS = {
    "set_yarn": {"name", "fibre", "weight"},
    "set_needles": {"size", "system"},
    "set_gauge": {"stitches", "rows", "over", "unit"},
    "select_size": {"size"},
    "get_project_status": set(),
    "generate_working_pattern": set(),
    "start_over": set(),
}


class BuildError(Exception):
    pass


def load(name: str):
    return yaml.safe_load((SRC / name).read_text(encoding="utf-8"))


def split(cases: list[dict], key, test_share: float = 0.4) -> None:
    """Stratified dev/test split by `key(case)`, fixed seed."""
    groups = defaultdict(list)
    for c in cases:
        groups[key(c)].append(c)
    rng = random.Random(SEED)
    for group in groups.values():
        rng.shuffle(group)
        n_test = round(len(group) * test_share)
        for i, c in enumerate(group):
            c["split"] = "test" if i < n_test else "dev"


# ---------- intents ----------

def build_intents() -> list[dict]:
    src = load("intents.yaml")
    if sorted(src) != sorted(INTENTS):
        raise BuildError(f"intent labels differ from CONVENTIONS: {sorted(set(src) ^ set(INTENTS))}")
    cases, seen = [], set()
    for label, items in src.items():
        for it in items:
            t = it["text"].strip()
            if t.lower() in seen:
                raise BuildError(f"duplicate intent text: {t}")
            seen.add(t.lower())
            cases.append({"component": "router", "source": "handwritten", "input": {"text": t},
                          "expected": {"intent": label}, "tags": it.get("tags", []), "notes": ""})
    split(cases, key=lambda c: c["expected"]["intent"])
    return cases


# ---------- setup dialogues ----------

def _apply(state: dict, call: dict, stage: str) -> dict:
    """Expected project fields after a tool call (code does all unit conversion)."""
    if stage == "locked" and call["tool"] in {"set_yarn", "set_needles", "set_gauge", "select_size"}:
        return state
    a = call["args"]
    if call["tool"] == "set_yarn":
        state["yarn"] = {"name": a.get("name"), "fibre": a.get("fibre"), "weight": a.get("weight")}
    elif call["tool"] == "set_needles":
        state["needle_mm"] = float(a["size"]) if a["system"] == "mm" else units.us_needle_to_mm(a["size"])
    elif call["tool"] == "set_gauge":
        state["gauge_sts_10cm"] = units.gauge_to_per_10cm(a["stitches"], a.get("over", 10), a.get("unit", "cm"))
        if a.get("rows") is not None:
            state["gauge_rows_10cm"] = units.gauge_to_per_10cm(a["rows"], a.get("over", 10), a.get("unit", "cm"))
    elif call["tool"] == "select_size":
        state["size"] = a["size"]
    return state


def build_setup() -> list[dict]:
    cases = []
    for d in load("setup_dialogues.yaml"):
        state: dict = {}
        for call in d["calls"]:
            if call["tool"] not in TOOLS:
                raise BuildError(f"{d['id']}: unknown tool {call['tool']}")
            extra = set(call["args"]) - TOOLS[call["tool"]]
            if extra:
                raise BuildError(f"{d['id']}: unknown args {extra} for {call['tool']}")
            if call["tool"] == "select_size" and call["args"]["size"] not in d.get("sizes", []):
                raise BuildError(f"{d['id']}: size {call['args']['size']} not in {d.get('sizes')}")
            state = _apply(state, call, d["stage"])
        cases.append({"component": "setup_agent", "source": "handwritten", "case_ref": d["id"],
                      "input": {"stage": d["stage"], "sizes": d.get("sizes", []), "turns": d["turns"]},
                      "expected": {"calls": d["calls"], "state": state,
                                   "linker": d.get("expect_linker"),
                                   "state_change": d.get("expect_state_change", True)},
                      "tags": d.get("tags", []), "notes": ""})
    split(cases, key=lambda c: c["tags"][0])
    return cases


# ---------- KB queries ----------

def build_kb() -> list[dict]:
    src, ids = load("kb_queries.yaml"), set(kb.abbreviations())
    cases = []
    for it in src["exact"]:
        if it["gold"] not in ids:
            raise BuildError(f"unknown KB id {it['gold']}")
        cases.append({"component": "kb_lookup", "source": "handwritten", "input": {"query": it["query"], "kind": "exact"},
                      "expected": {"primary": it["gold"], "relevant": [it["gold"]]}, "tags": it.get("tags", []), "notes": ""})
    for it in src["question"]:
        bad = [i for i in it["relevant"] + [it["primary"]] if i not in ids]
        if bad or it["primary"] not in it["relevant"]:
            raise BuildError(f"bad KB ids or primary in {it['query']}: {bad}")
        cases.append({"component": "kb_lookup", "source": "handwritten", "input": {"query": it["query"], "kind": "question"},
                      "expected": {"primary": it["primary"], "relevant": it["relevant"]}, "tags": it.get("tags", []), "notes": ""})
    split(cases, key=lambda c: c["input"]["kind"])
    return cases


# ---------- yarns ----------

def _yarn_rows() -> list[dict]:
    return list(csv.DictReader(open(ROOT / "data" / "yarns.csv", encoding="utf-8")))


def _resolve(rows: list[dict], ref: list[str]) -> dict:
    hits = [r for r in rows if r["brand"] == ref[0] and r["name"] == ref[1]]
    if len(hits) != 1:
        raise BuildError(f"yarn {ref} matches {len(hits)} rows in yarns.csv")
    return hits[0]


def build_yarn_links(rows: list[dict]) -> list[dict]:
    cases = []
    for it in load("yarns.yaml")["mentions"]:
        if "ambiguous" in it:
            expected = {"yarn_id": None, "ambiguous": sorted(int(_resolve(rows, r)["yarn_id"]) for r in it["ambiguous"])}
        elif it["gold"] is None:
            expected = {"yarn_id": None, "ambiguous": []}
        else:
            expected = {"yarn_id": int(_resolve(rows, it["gold"])["yarn_id"]), "ambiguous": []}
        cases.append({"component": "yarn_linker", "source": "handwritten", "input": {"text": it["text"]},
                      "expected": expected, "tags": it.get("tags", []), "notes": ""})
    split(cases, key=lambda c: "none" if c["expected"]["yarn_id"] is None else "match")
    return cases


def _fibre_text(fibre: str) -> str:
    f = kb.fibres()[fibre]
    text = " ".join([fibre, *f["aliases"], f["care"], f["blocking"], *f["tips"], *f["good_for"], *f["avoid_for"]])
    if f["elasticity"] == "low":
        text += " low elasticity"
    return text.lower()


def build_yarn_advice(rows: list[dict]) -> list[dict]:
    cats = {c["id"]: c for c in kb.yarn_weights()["categories"]}
    by_name = {n: c for c in cats.values() for n in c["ravelry_names"]}
    cases = []
    for it in load("yarns.yaml")["advice"]:
        if "yarn" in it:
            r = _resolve(rows, it["yarn"])
            cat, fibre = cats[int(r["cyc_category"])], r["main_fibre"]
            gold = {"yarn_id": int(r["yarn_id"]), "cyc_category": cat["id"],
                    "needle_mm": [float(r["needle_min_mm"]), float(r["needle_max_mm"])],
                    "needle_source": r["needle_source"],
                    "gauge_sts_10cm": [float(r["gauge_min_sts_10cm"]), float(r["gauge_max_sts_10cm"])],
                    "gauge_source": r["gauge_source"], "cyc_gauge_sts_10cm": cat["sts_per_10cm"]}
            if bool(it.get("warn_gauge")) != bool(r["gauge_flag"]):
                raise BuildError(f"warn_gauge for {it['yarn']} disagrees with yarns.csv flag {r['gauge_flag']!r}")
            inp = {"yarn": it["yarn"], "question": it["question"]}
        else:
            cat, fibre = by_name[it["weight"]], it["fibre"]
            gold = {"yarn_id": None, "cyc_category": cat["id"], "needle_mm": cat["needle_mm"], "needle_source": "cyc",
                    "gauge_sts_10cm": cat["sts_per_10cm"], "gauge_source": "cyc", "cyc_gauge_sts_10cm": cat["sts_per_10cm"]}
            inp = {"fibre": fibre, "weight": it["weight"], "question": it["question"]}
        if fibre not in kb.fibres():
            raise BuildError(f"fibre {fibre} not in fibres.yaml")
        source_text = _fibre_text(fibre) + " " + (cat.get("note") or "").lower()
        missing = [m for m in it["must_mention"] if m.lower() not in source_text]
        if missing:
            raise BuildError(f"must_mention {missing} for {inp} not supported by the KB")
        gold.update({"main_fibre": fibre, "must_mention": it["must_mention"], "warn_gauge": bool(it.get("warn_gauge"))})
        cases.append({"component": "yarn_advisor", "source": "handwritten", "input": inp, "expected": gold,
                      "tags": it.get("tags", []), "notes": ""})
    split(cases, key=lambda c: c["tags"][0])
    return cases


# ---------- output ----------

def write(name: str, prefix: str, cases: list[dict]) -> None:
    for i, c in enumerate(cases, 1):
        c["id"] = f"{prefix}-{i:03d}"
    with open(OUT / name, "w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps({"id": c.pop("id"), "split": c.pop("split"), **c}, ensure_ascii=False) + "\n")
    sp = Counter(json.loads(line)["split"] for line in open(OUT / name, encoding="utf-8"))
    print(f"{name:26} {sum(sp.values()):3} cases  dev={sp['dev']:3} test={sp['test']:3}")


def review_sample(all_sets: dict[str, list[dict]]) -> None:
    rng = random.Random(SEED)
    lines = ["# Eval labels: human review sample (20%)", "",
             "Generated by `python -m knit_copilot.data.build_eval_sets`. Check each label; record fixes in "
             "`docs/03_data_preparation.md`.", ""]
    for name, cases in all_sets.items():
        sample = rng.sample(cases, max(1, round(len(cases) * 0.2)))
        lines += [f"## {name} ({len(sample)} of {len(cases)})", "", "| ✓ | input | expected |", "|---|---|---|"]
        for c in sample:
            inp = json.dumps(c["input"], ensure_ascii=False).replace("|", "\\|")
            exp = json.dumps({k: v for k, v in c["expected"].items() if k != "state"}, ensure_ascii=False).replace("|", "\\|")
            lines.append(f"| ☐ | {inp} | {exp} |")
        lines.append("")
    (ROOT / "docs" / "data" / "eval_review_sample.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    rows = _yarn_rows()
    sets = {
        "intent_cases.jsonl": ("intent", build_intents()),
        "setup_cases.jsonl": ("setup", build_setup()),
        "kb_queries.jsonl": ("kb", build_kb()),
        "yarn_link_cases.jsonl": ("yarnlink", build_yarn_links(rows)),
        "yarn_advice_cases.jsonl": ("advice", build_yarn_advice(rows)),
    }
    review_sample({name: cases for name, (_, cases) in sets.items()})
    for name, (prefix, cases) in sets.items():
        write(name, prefix, cases)
    print("review sample -> docs/data/eval_review_sample.md")


if __name__ == "__main__":
    main()
