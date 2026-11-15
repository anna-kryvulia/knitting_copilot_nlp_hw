"""Synthetic pattern generator: gold Pattern IR → pattern text in several writing styles → eval cases.

Purpose: parser eval data with exact gold labels (IR, per-row stitch counts), since no labelled dataset of
written knitting patterns exists (docs/02_data_understanding.md §2.4).
Input: templates (data/templates.py), a seed. Output: data/eval/parse_cases.jsonl.

Styles (one per case):
  terse     US abbreviations, "*...; rep from * to last 2 sts"
  brackets  US abbreviations, "(...) to end", "[...] 3 times"
  verbose   spelled-out instructions, "repeat [...] until 2 stitches remain"
  uk        UK terms (yfwd, skpo, cast off, tension, stocking stitch)
  imperial  terse + gauge per 4 in, US needle sizes, lengths in inches (gold IR converted to metric)
Noise: ~25% of cases get typos (casing, spacing, punctuation), tagged `typo`.

Run: python -m knit_copilot.data.generator [--n 60] [--seed 7]
"""

import argparse
import json
import random
import re
from collections import Counter

from knit_copilot import units
from knit_copilot.config import ROOT
from knit_copilot.data.templates import MARKER_TEMPLATES, TEMPLATES
from knit_copilot.ir import Op, Pattern, RepeatRowsStep, Repeat, RowsStep, BindOffStep
from knit_copilot.simulator import simulate

OUT = ROOT / "data" / "eval" / "parse_cases.jsonl"
STYLES = ["terse", "brackets", "verbose", "uk", "imperial"]

TERSE = {"k": "k", "p": "p", "yo": "yo", "k2tog": "k2tog", "ssk": "ssk", "skp": "skp", "kfb": "kfb",
         "c6b": "C6B", "c6f": "C6F", "c4b": "C4B", "c4f": "C4F", "bo": "BO", "pm": "pm", "sm": "sm", "rm": "rm"}
UK = {**TERSE, "yo": "yfwd", "skp": "skpo", "bo": "cast off"}
VERBOSE = {"k": "knit", "p": "purl", "yo": "yarn over", "k2tog": "knit 2 together", "ssk": "slip slip knit",
           "skp": "slip 1, knit 1, pass slipped stitch over", "kfb": "knit into front and back",
           "c6b": "cable 6 back", "c6f": "cable 6 front", "c4b": "cable 4 back", "c4f": "cable 4 front",
           "pm": "place marker", "sm": "slip marker", "rm": "remove marker"}
NUM_WORDS = {2: "twice", 3: "three times", 4: "four times", 5: "five times", 6: "six times"}


# ---------- numbers ----------

def fmt(value, sizes: list[str]) -> str:
    """40 → '40'; {'S': 80, 'M': 88, 'L': 96} → '80 (88, 96)'."""
    if isinstance(value, dict):
        vals = [value[s] for s in sizes]
        first, rest = vals[0], vals[1:]
        return f"{_n(first)} ({', '.join(_n(v) for v in rest)})" if rest else _n(first)
    return _n(value)


def _n(v) -> str:
    return str(int(v)) if float(v).is_integer() else str(v)


# ---------- ops and repeats ----------

class Renderer:
    def __init__(self, style: str, sizes: list[str], rng: random.Random, construction: str = "flat"):
        self.style, self.sizes, self.rng = style, sizes, rng
        self.unit = "round" if construction == "round" else "row"
        self.names = UK if style == "uk" else VERBOSE if style == "verbose" else TERSE

    def op(self, o: Op) -> str:
        name = self.names.get(o.op, o.op)
        n = fmt(o.n, self.sizes)
        if o.op in ("k", "p"):
            return f"{name} {n}" if self.style == "verbose" else f"{name}{n}"
        if o.n == 1:
            return name
        if self.style == "verbose":
            return f"{name} {NUM_WORDS.get(o.n, f'{n} times')}"
        return f"[{name}] {n} times" if self.style == "brackets" else f"{name} {n} times"

    def items(self, items, nested=False) -> str:
        return ", ".join(self.item(it, nested) for it in items)

    def item(self, it, nested=False) -> str:
        if isinstance(it, Op):
            return self.op(it)
        rem = it.until.remaining if it.until else None
        if it.until is not None and it.until.marker:
            return self.to_marker(it, rem, nested)
        # single-op repeat to the end / to last n sts: "k to end", "p to last 2 sts"
        if len(it.repeat) == 1 and isinstance(it.repeat[0], Op) and it.repeat[0].n == 1 and rem is not None:
            word = self.names.get(it.repeat[0].op, it.repeat[0].op)
            if rem == 0:
                return f"{word} to the end of the {self.unit}" if self.style == "verbose" else f"{word} to end"
            r = fmt(rem, self.sizes)
            if self.style == "verbose":
                return f"{word} until {r} stitch{'' if rem == 1 else 'es'} remain{'s' if rem == 1 else ''}"
            return f"{word} to last st" if rem == 1 else f"{word} to last {r} sts"
        inner = self.items(it.repeat, nested=True)
        if it.times is not None:
            t = fmt(it.times, self.sizes)
            if self.style == "verbose":
                return f"work [{inner}] {NUM_WORDS.get(it.times, f'{t} times')}"
            if self.style == "brackets" or nested:
                return f"({inner}) {t} times"
            more = it.times - 1
            return f"*{inner}; rep from * {more} more time{'s' if more != 1 else ''}" if more else inner
        r = fmt(rem, self.sizes)
        if self.style == "verbose":
            return f"repeat [{inner}] to the end of the {self.unit}" if rem == 0 else f"repeat [{inner}] until {r} stitches remain"
        if self.style == "brackets":
            return f"({inner}) to end" if rem == 0 else f"[{inner}] to {'last st' if rem == 1 else f'last {r} sts'}"
        last = "last st" if rem == 1 else f"last {r} sts"
        return f"*{inner}; rep from * to end" if rem == 0 else f"*{inner}; rep from * to {last}"

    def to_marker(self, it, rem, nested: bool) -> str:
        """'k to marker', 'k to 2 sts before marker', '*k1, p1; rep from * to 4 sts before m'."""
        r = fmt(rem, self.sizes)
        m = self.rng.choice(["marker", "m"]) if self.style != "verbose" else "the marker"
        if len(it.repeat) == 1 and isinstance(it.repeat[0], Op) and it.repeat[0].n == 1:
            word = self.names.get(it.repeat[0].op, it.repeat[0].op)
            if self.style == "verbose":
                return f"{word} to the marker" if rem == 0 else f"{word} until {r} stitches before the marker"
            return f"{word} to {m}" if rem == 0 else f"{word} to {r} sts before {m}"
        inner = self.items(it.repeat, nested=True)
        stop = m if rem == 0 else f"{r} sts before {m}"
        if self.style == "verbose":
            return f"repeat [{inner}] until " + ("the marker" if rem == 0 else f"{r} stitches before the marker")
        if self.style == "brackets" or nested:
            return f"[{inner}] to {stop}"
        return f"*{inner}; rep from * to {stop}"

    # ---------- rows and steps ----------

    def row(self, r, construction: str) -> str:
        text = self.items(r.ops)
        text = text[0].upper() + text[1:]
        numbered = re.fullmatch(r"(Row|Rnd) \d+", r.label)
        side = "" if r.side == "round" or not numbered else (
            {"RS": " (right side)", "WS": " (wrong side)"}[r.side] if self.style == "verbose" else f" ({r.side})")
        count = ""
        if r.stated_count is not None:
            c = fmt(r.stated_count, self.sizes)
            count = self.rng.choice([f" ({c} sts)", f" — {c} sts", f" [{c} sts]"])
        return f"{r.label}{side}: {text}.{count}"

    def ref(self, labels: list[str]) -> str:
        if len(labels) == 1:
            return labels[0]
        nums = [re.fullmatch(r"(Row|Rnd) (\d+)", lb) for lb in labels]
        if all(nums) and len({m.group(1) for m in nums}) == 1:
            word = "Rows" if nums[0].group(1) == "Row" else "Rnds"
            return f"{word} {nums[0].group(2)}–{nums[-1].group(2)}" if len(labels) > 2 else \
                f"{word} {nums[0].group(2)} and {nums[1].group(2)}"
        return ", ".join(labels[:-1]) + f" and {labels[-1]}"

    def length(self, cm) -> str:
        if self.style == "imperial":
            return fmt(cm, self.sizes) + " in"
        return fmt(cm, self.sizes) + " cm"

    def repeat_rows(self, s: RepeatRowsStep, count_before: int | None = None) -> str:
        ref = self.ref(s.rows_ref)
        if s.times is not None:
            if self.style == "verbose" or self.rng.random() < 0.3:
                total = fmt({k: v + 1 for k, v in s.times.items()} if isinstance(s.times, dict) else s.times + 1,
                            self.sizes)
                return f"Work {ref} a total of {total} times."
            t = fmt(s.times, self.sizes)
            return f"Repeat {ref} {t} more time{'s' if s.times != 1 else ''}."
        if s.until_count is not None:
            c = fmt(s.until_count, self.sizes)
            target = s.until_count if isinstance(s.until_count, int) else s.until_count[self.sizes[0]]
            options = [f"Repeat {ref} until there are {c} sts on the needle."]
            if count_before is not None and target < count_before:
                options.append(f"Repeat {ref} until {c} sts remain.")
            else:
                options.append(f"Repeat {ref} until you have {c} sts.")
            return self.rng.choice(options)
        where = "from cast-on edge" if s.measured_from == "cast_on" else "from the start of this section"
        verb = self.rng.choice(["piece measures", "work measures"])
        return f"Repeat {ref} until {verb} {self.length(s.until_length_cm)} {where}."

    def bind_off(self, s: BindOffStep, last_count) -> str:
        if s.method == "gather":
            return "Break yarn, draw the tail through the remaining stitches and pull tight."
        word = "Cast off" if self.style == "uk" else ("Bind off" if self.style == "verbose" else "BO")
        how = {"loose": " loosely", "in pattern": " in pattern", "standard": ""}.get(s.method, "")
        return f"{word} all {'stitches' if self.style == 'verbose' else 'sts'}{how}."


def _imperial(pattern: Pattern) -> tuple[Pattern, dict]:
    """Imperial version: gauge per 4 in, US needles, lengths in inches. Returns gold IR (metric, converted
    back from the rounded imperial values) and the imperial numbers to print."""
    p = pattern.model_copy(deep=True)
    g = p.gauge
    sts4, rows4 = round(g.sts_per_10cm * 1.016), round(g.rows_per_10cm * 1.016)
    g.sts_per_10cm, g.rows_per_10cm = units.gauge_per_4in_to_10cm(sts4), units.gauge_per_4in_to_10cm(rows4)
    us = next((k for k, v in units.US_NEEDLE_MM.items() if v == g.needle_mm), None)
    shown = {"sts4": sts4, "rows4": rows4, "needle": f"US {us}" if us else f"{g.needle_mm} mm"}
    for s in p.pieces[0].steps:
        if isinstance(s, RepeatRowsStep) and s.until_length_cm is not None:
            def to_in(cm):
                return round(cm / 2.54 * 2) / 2
            if isinstance(s.until_length_cm, dict):
                inches = {k: to_in(v) for k, v in s.until_length_cm.items()}
                s.until_length_cm = {k: units.inch_to_cm(v) for k, v in inches.items()}
            else:
                inches = to_in(s.until_length_cm)
                s.until_length_cm = units.inch_to_cm(inches)
            shown.setdefault("lengths", []).append(inches)
    return p, shown


def render(pattern: Pattern, style: str, rng: random.Random) -> tuple[str, Pattern]:
    """Pattern text in `style`, plus the gold IR that matches the text exactly (metric)."""
    gold, shown = (_imperial(pattern) if style == "imperial" else (pattern, {}))
    R = Renderer(style, gold.sizes, rng, gold.construction)
    g = gold.gauge
    piece = gold.pieces[0]
    lines = [gold.title.upper() if rng.random() < 0.5 else gold.title, ""]
    if gold.sizes:
        lines.append(f"Sizes: {gold.sizes[0]} ({', '.join(gold.sizes[1:])})")
    if style == "imperial":
        lines.append(f"Needles: {shown['needle']}")
        lines.append(f"Gauge: {shown['sts4']} sts and {shown['rows4']} rows = 4 in in {g.stitch_pattern}.")
    else:
        word = "Tension" if style == "uk" else "Gauge"
        lines.append(f"Needles: {_n(g.needle_mm)} mm")
        lines.append(f"{word}: {_n(g.sts_per_10cm)} sts and {_n(g.rows_per_10cm)} rows = 10 cm "
                     f"in {g.stitch_pattern.replace('stockinette', 'stocking stitch') if style == 'uk' else g.stitch_pattern}.")
    lines.append("")

    co = fmt(piece.cast_on, gold.sizes)
    if style == "verbose":
        lines.append(f"Cast on {co} stitches.")
    else:
        lines.append(f"CO {co} sts." if style in ("terse", "imperial", "brackets") else f"Cast on {co} sts.")
    if gold.construction == "round":
        lines.append("Join to work in the round, being careful not to twist, and place a marker for the beginning of the round.")

    lengths = iter(shown.get("lengths", []))
    last_count = None
    sim = simulate(gold, gold.sizes[0] if gold.sizes else None)
    count_before = {}                       # step index -> stitch count when the step starts
    for r in sim.rows:
        count_before.setdefault(r.step, r.start_count)
    for i, s in enumerate(piece.steps):
        if isinstance(s, RowsStep):
            for r in s.rows:
                lines.append(R.row(r, gold.construction))
        elif isinstance(s, RepeatRowsStep):
            text = R.repeat_rows(s, count_before.get(i))
            if style == "imperial" and s.until_length_cm is not None:
                inch = next(lengths)
                text = re.sub(r"measures .*? in", f"measures {fmt(inch, gold.sizes)} in", text)
            lines.append(text)
        elif isinstance(s, BindOffStep):
            lines.append(R.bind_off(s, last_count))
    lines += ["", rng.choice(["Weave in ends and block.", "Finishing: weave in all ends. Block to measurements.",
                              "Weave in the ends. Wet block if desired."])]
    return "\n".join(lines), gold


# ---------- noise ----------

def add_typos(text: str, rng: random.Random) -> str:
    """Realistic, meaning-preserving noise: casing, spacing, punctuation."""
    out = []
    for line in text.split("\n"):
        if re.match(r"(Row|Rnd|Rows|Rnds)\b", line) and rng.random() < 0.5:
            line = rng.choice([
                lambda s: s.replace("k2tog", "K2tog"), lambda s: s.replace("k2tog", "k2 tog"),
                lambda s: s.replace(", ", ",", 1), lambda s: s.replace("; rep", " rep"),
                lambda s: s.replace("sts", "st", 1), lambda s: s.rstrip("."),
                lambda s: s.replace("rep from", "Rep from"), lambda s: s.replace(": ", " - ", 1),
            ])(line)
        out.append(line)
    return "\n".join(out)


# ---------- cases ----------

def make_cases(n: int, seed: int, templates: dict | None = None, prefix: str = "parse") -> list[dict]:
    templates = templates or TEMPLATES
    rng = random.Random(seed)
    names = list(templates)
    cases = []
    for i in range(n):
        template = names[i % len(names)]
        style = STYLES[i % len(STYLES)]          # 9 templates x 5 styles are coprime: every pair occurs
        case_rng = random.Random(rng.random())
        pattern = templates[template](case_rng)
        text, gold = render(pattern, style, case_rng)
        tags = [template, style, gold.construction]
        if gold.sizes:
            tags.append("multi_size")
        if case_rng.random() < 0.25:
            text = add_typos(text, case_rng)
            tags.append("typo")
        size = case_rng.choice(gold.sizes) if gold.sizes else None
        sim = simulate(gold, size)
        if not sim.ok or sim.count_mismatches():
            raise RuntimeError(f"gold pattern does not simulate: {template} {style}: {sim.errors}")
        cases.append({
            "id": f"{prefix}-{i + 1:03d}", "split": None, "component": "parser", "source": "synthetic",
            "input": {"text": text, "size": size},
            "expected": {"ir": gold.model_dump(mode="json", exclude_defaults=False),
                         "size": size, "total_rows": len(sim.rows), "final_count": sim.final_count,
                         "row_counts": [[r.number, r.label, r.end_count] for r in sim.rows]},
            "tags": tags, "notes": "",
        })
    # stratified split: per template, ~60% dev / 40% test
    by_template: dict[str, list[dict]] = {}
    for c in cases:
        by_template.setdefault(c["tags"][0], []).append(c)
    for group in by_template.values():
        random.Random(seed).shuffle(group)
        cut = round(len(group) * 0.6)
        for j, c in enumerate(group):
            c["split"] = "dev" if j < cut else "test"
    return cases


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=63)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--markers", action="store_true", help="marker templates → data/eval/parse_cases_markers.jsonl")
    args = ap.parse_args()
    global OUT
    if args.markers:
        OUT = ROOT / "data" / "eval" / "parse_cases_markers.jsonl"
        cases = make_cases(20, args.seed, MARKER_TEMPLATES, prefix="markers")
    else:
        cases = make_cases(args.n, args.seed)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    tags = Counter(t for c in cases for t in c["tags"])
    print(f"{len(cases)} cases -> {OUT.relative_to(ROOT)}")
    print("split:", dict(Counter(c["split"] for c in cases)))
    print("tags:", dict(tags))


if __name__ == "__main__":
    main()
