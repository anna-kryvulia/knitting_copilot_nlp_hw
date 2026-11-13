"""Grammar-based pattern parser (baseline and fallback for the LLM parser).

Purpose: turn pattern text in standard notation into Pattern IR with rules only: no model calls.
Used (1) as the baseline the LLM parser is compared against, (2) as the fast path in the hybrid parser.
Input: pattern text. Output: ParseResult (Pattern IR or None, plus warnings for lines it could not read).
Model calls: none. Tool calls: none.

Pipeline: header fields (sizes, needles, gauge, cast-on) → verbose phrases normalised to abbreviations →
each row body split into items (star repeats, bracket groups, "X to end", "k2 (3, 4)") → abbreviations
resolved with the KB → repeat/bind-off lines → IR validated by Pydantic.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ValidationError

from knit_copilot import kb, units
from knit_copilot.ir import Pattern

NUM = r"\d+(?:\.\d+)?"
MULTI = rf"{NUM}(?:\s*\(\s*{NUM}(?:\s*,\s*{NUM})*\s*\))?"          # 40  or  40 (44, 48)
WORD_TIMES = {"once": 1, "twice": 2, "three times": 3, "four times": 4, "five times": 5, "six times": 6,
              "seven times": 7, "eight times": 8}


class ParseResult(BaseModel):
    pattern: Pattern | None
    warnings: list[str] = []

    @property
    def ok(self) -> bool:
        return self.pattern is not None


class GrammarError(ValueError):
    pass


# ---------- numbers ----------

def parse_multi(text: str, sizes: list[str]):
    """'40' → 40; '40 (44, 48)' with sizes S/M/L → {'S': 40, 'M': 44, 'L': 48}."""
    nums = [float(x) for x in re.findall(NUM, text)]
    vals = [int(x) if x.is_integer() else x for x in nums]
    if len(vals) == 1:
        return vals[0]
    if len(vals) != len(sizes):
        raise GrammarError(f"{len(vals)} values for {len(sizes)} sizes in {text!r}")
    if len(set(vals)) == 1:
        return vals[0]
    return dict(zip(sizes, vals))


# ---------- verbose → terse normalisation ----------

VERBOSE_RULES = [
    (r"slip 1, knit 1, pass slipped stitch over", "skp"),
    (r"knit 2 together", "k2tog"), (r"purl 2 together", "p2tog"), (r"slip slip knit", "ssk"),
    (r"yarn over", "yo"), (r"knit into front and back", "kfb"),
    (r"cable (\d) (back|front)", lambda m: f"c{m.group(1)}{m.group(2)[0]}"),
    (rf"repeat \[(.+?)\] to the end of the (?:row|round)", r"(\1) to end"),
    (rf"repeat \[(.+?)\] until ({MULTI}) stitch(?:es)? remains?", r"[\1] to last \2 sts"),
    (r"work \[(.+?)\] (once|twice|three times|four times|five times|six times|seven times|eight times)",
     lambda m: f"({m.group(1)}) {WORD_TIMES[m.group(2)]} times"),
    (rf"work \[(.+?)\] ({MULTI}) times", r"(\1) \2 times"),
    (r"\b(knit|purl) to the end of the (?:row|round)", lambda m: f"{m.group(1)[0]} to end"),
    (rf"\b(knit|purl) until ({MULTI}) stitch(?:es)? remains?", lambda m: f"{m.group(1)[0]} to last {m.group(2)} sts"),
    (rf"\b(knit|purl) ({MULTI})", lambda m: f"{m.group(1)[0]}{m.group(2)}"),
    # any other stitch, after the phrases above became abbreviations: "k2tog to the end of the round"
    (r"(\S+) to the end of the (?:row|round)", r"\1 to end"),
    (rf"(\S+) until ({MULTI}) stitch(?:es)? remains?", r"\1 to last \2 sts"),
]


def normalise_body(text: str) -> str:
    t = text.strip().rstrip(".").strip()
    for pat, rep in VERBOSE_RULES:
        t = re.sub(pat, rep, t, flags=re.I)
    return t


# ---------- instruction body → IR items ----------

def _split_top(text: str) -> list[str]:
    """Split on commas that are not inside () or []."""
    parts, depth, cur = [], 0, ""
    for ch in text:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return [p.strip() for p in parts if p.strip()]


STAR = re.compile(
    rf"\*(?P<inner>.+?);?\s*rep(?:eat)? from \*\s*(?P<stop>to end|to last st\b|to last (?P<rem>{MULTI}) sts?|"
    rf"(?P<more>{MULTI}) (?:more times?|times more)|once more)", re.I)


def parse_items(text: str, sizes: list[str]) -> list[dict]:
    """Instruction text → list of IR items (ops and repeats)."""
    text = normalise_body(text)
    stars: list[dict] = []

    def star_sub(m: re.Match) -> str:
        inner = parse_items(m.group("inner"), sizes)
        stop = m.group("stop").lower()
        if stop == "to end":
            rep = {"repeat": inner, "until": {"remaining": 0}}
        elif stop.startswith("to last st") and not m.group("rem"):
            rep = {"repeat": inner, "until": {"remaining": 1}}
        elif m.group("rem"):
            rep = {"repeat": inner, "until": {"remaining": parse_multi(m.group("rem"), sizes)}}
        else:
            more = 1 if stop == "once more" else parse_multi(m.group("more"), sizes)
            total = {k: v + 1 for k, v in more.items()} if isinstance(more, dict) else more + 1
            rep = {"repeat": inner, "times": total}
        stars.append(rep)
        return f"§{len(stars) - 1}"

    text = STAR.sub(star_sub, text)
    if "*" in text:
        raise GrammarError(f"unmatched '*' repeat in {text!r}")
    return [_atom(p, sizes, stars) for p in _split_top(text)]


GROUP = re.compile(rf"^[\(\[](?P<inner>.+)[\)\]]\s*(?P<stop>to end|to last st\b|to last (?P<rem>{MULTI}) sts?|"
                   rf"(?P<times>{MULTI}) times|(?P<word>once|twice|three times|four times|five times|six times))$", re.I)
TO_END = re.compile(rf"^(?P<op>.+?) to (?:end|last st\b|last (?P<rem>{MULTI}) sts?)$", re.I)
OP_TIMES = re.compile(rf"^(?P<op>.+?) (?P<times>{MULTI}) times$", re.I)
OP_NUM = re.compile(rf"^(?P<op>[a-z]+?)\s*(?P<n>{MULTI})$", re.I)


def _op(name: str) -> str:
    a = kb.lookup(name)
    if a is None or not a.is_stitch_op:
        raise GrammarError(f"unknown abbreviation {name!r}")
    return a.id


def _atom(tok: str, sizes: list[str], stars: list[dict]) -> dict:
    tok = tok.strip().rstrip(";.").strip()
    if re.fullmatch(r"§\d+", tok):
        return stars[int(tok[1:])]
    m = GROUP.match(tok)
    if m:
        inner = parse_items(m.group("inner"), sizes)
        if m.group("times") or m.group("word"):
            t = parse_multi(m.group("times"), sizes) if m.group("times") else WORD_TIMES[m.group("word").lower()]
            return {"repeat": inner, "times": t}
        rem = parse_multi(m.group("rem"), sizes) if m.group("rem") else (1 if "last st" in m.group("stop").lower() else 0)
        return {"repeat": inner, "until": {"remaining": rem}}
    m = TO_END.match(tok)
    if m:
        rem = parse_multi(m.group("rem"), sizes) if m.group("rem") else (1 if "last st" in tok.lower() else 0)
        return {"repeat": [{"op": _op(m.group("op"))}], "until": {"remaining": rem}}
    m = OP_TIMES.match(tok)
    if m and kb.lookup(m.group("op")):
        return {"op": _op(m.group("op")), "n": parse_multi(m.group("times"), sizes)}
    if kb.lookup(tok):                                          # k2tog, ssk, C6B, yfwd ...
        return {"op": _op(tok)}
    m = OP_NUM.match(tok)                                       # k2, p10, k2 (3, 4)
    if m and kb.lookup(m.group("op")):
        return {"op": _op(m.group("op")), "n": parse_multi(m.group("n"), sizes)}
    raise GrammarError(f"cannot read instruction {tok!r}")


# ---------- lines ----------

ROW = re.compile(r"^(?P<label>(?:Row|Rnd|Round) \d+|[A-Z][A-Za-z ]*? row)\s*(?:\((?P<side>RS|WS|right side|wrong side)\))?"
                 r"\s*(?::|-|–|—)\s*(?P<body>.+)$", re.I)
COUNT = re.compile(rf"\s*(?:[\(\[]\s*(?P<a>{MULTI})\s*sts?\s*[\)\]]|[—–-]\s*(?P<b>{MULTI})\s*sts?)\s*\.?\s*$", re.I)
REPEAT_LINE = re.compile(r"^(?:Repeat|Rep|Work) (?P<ref>.+?) (?P<rest>(?:until|a total of|\d+ (?:more )?times|once more).*)$", re.I)


def _label(text: str) -> str:
    text = text.strip()
    m = re.fullmatch(r"(row|rnd|round) (\d+)", text, re.I)
    if m:
        word = "Rnd" if m.group(1).lower() in ("rnd", "round") else "Row"
        return f"{word} {m.group(2)}"
    return text[0].upper() + text[1:]


def _refs(ref: str) -> list[str]:
    ref = ref.strip()
    m = re.fullmatch(r"(Rows|Rnds|Rounds) (\d+)\s*[–-]\s*(\d+)", ref, re.I)
    if m:
        word = "Row" if m.group(1).lower() == "rows" else "Rnd"
        return [f"{word} {i}" for i in range(int(m.group(2)), int(m.group(3)) + 1)]
    m = re.fullmatch(r"(Rows|Rnds|Rounds) (\d+) and (\d+)", ref, re.I)
    if m:
        word = "Row" if m.group(1).lower() == "rows" else "Rnd"
        return [f"{word} {m.group(2)}", f"{word} {m.group(3)}"]
    return [_label(r) for r in re.split(r",\s*|\s+and\s+", ref)]


def _repeat_step(m: re.Match, sizes: list[str], imperial: bool) -> dict:
    step: dict = {"type": "repeat_rows", "rows_ref": _refs(m.group("ref"))}
    rest = m.group("rest")
    if mm := re.match(rf"a total of ({MULTI}) times", rest, re.I):
        total = parse_multi(mm.group(1), sizes)
        step["times"] = {k: v - 1 for k, v in total.items()} if isinstance(total, dict) else total - 1
    elif mm := re.match(rf"({MULTI}) more times?|({MULTI}) times", rest, re.I):
        step["times"] = parse_multi(mm.group(1) or mm.group(2), sizes)
    elif re.match(r"once more", rest, re.I):
        step["times"] = 1
    elif mm := re.search(rf"measures ({MULTI})\s*(cm|in|inches|\")", rest, re.I):
        length = parse_multi(mm.group(1), sizes)
        if mm.group(2).lower() in ("in", "inches", '"'):
            length = {k: units.inch_to_cm(v) for k, v in length.items()} if isinstance(length, dict) else units.inch_to_cm(length)
        step["until_length_cm"] = length
        step["measured_from"] = "cast_on" if "cast-on" in rest.lower() or "cast on" in rest.lower() else "previous_step"
    elif mm := re.search(rf"({MULTI}) sts", rest, re.I):
        step["until_count"] = parse_multi(mm.group(1), sizes)
    else:
        raise GrammarError(f"cannot read repeat rule {rest!r}")
    return step


def parse(text: str) -> ParseResult:
    """Parse a whole pattern. Lines that are not instructions (title, notes, finishing) are skipped."""
    lines = [ln.strip() for ln in text.splitlines()]
    warnings: list[str] = []
    title = next((ln for ln in lines if ln), "Untitled")
    sizes: list[str] = []
    gauge: dict | None = None
    needle_mm = None
    cast_on = None
    construction = "flat"
    steps: list[dict] = []
    imperial = bool(re.search(r"=\s*4\s*in", text, re.I))

    def rows_step() -> dict:
        if not steps or steps[-1]["type"] != "rows":
            steps.append({"type": "rows", "rows": []})
        return steps[-1]

    for ln in lines[1:]:
        if not ln:
            continue
        try:
            if m := re.match(r"^Sizes?:\s*(.+)$", ln, re.I):
                sizes = [s.strip() for s in re.split(r"[(),]", m.group(1)) if s.strip()]
            elif m := re.match(r"^Needles?:\s*(.+)$", ln, re.I):
                v = m.group(1)
                if mm := re.search(rf"({NUM})\s*mm", v):
                    needle_mm = float(mm.group(1))
                elif mm := re.search(r"US\s*(\d+(?:\.\d+)?)", v, re.I):
                    needle_mm = units.us_needle_to_mm(mm.group(1))
            elif m := re.match(rf"^(?:Gauge|Tension):\s*({NUM}) sts(?: and ({NUM}) rows)? = (10 cm|4 in)(?: in (.+?))?\.?$", ln, re.I):
                conv = (lambda x: units.gauge_per_4in_to_10cm(float(x))) if "in" in m.group(3) else float
                gauge = {"sts_per_10cm": conv(m.group(1)),
                         "rows_per_10cm": conv(m.group(2)) if m.group(2) else None,
                         "stitch_pattern": (m.group(4) or "stockinette").strip()}
            elif m := re.match(rf"^(?:CO|Cast on)\s+({MULTI})\s*(?:sts|stitches)", ln, re.I):
                cast_on = parse_multi(m.group(1), sizes)
            elif re.search(r"\bjoin\b.*\bround\b|\bin the round\b", ln, re.I) and not ROW.match(ln):
                construction = "round"
            elif m := ROW.match(ln):
                body, stated = m.group("body"), None
                if c := COUNT.search(body):
                    stated = parse_multi(c.group("a") or c.group("b"), sizes)
                    body = body[:c.start()]
                label = _label(m.group("label"))
                side = {"rs": "RS", "ws": "WS", "right side": "RS", "wrong side": "WS"}.get((m.group("side") or "").lower())
                if label.startswith("Rnd"):
                    side, construction = "round", "round"
                row = {"label": label, "side": side or ("round" if construction == "round" else "RS"),
                       "ops": parse_items(body, sizes)}
                if stated is not None:
                    row["stated_count"] = stated
                rows_step()["rows"].append(row)
            elif m := REPEAT_LINE.match(ln.rstrip(".")):
                steps.append(_repeat_step(m, sizes, imperial))
            elif re.match(r"^(BO|Bind off|Cast off)\b", ln, re.I):
                method = "loose" if "loose" in ln.lower() else "in pattern" if "in pattern" in ln.lower() else "standard"
                steps.append({"type": "bind_off", "method": method})
            elif re.match(r"^Break (?:the )?yarn.*(draw|thread|pull)", ln, re.I):
                steps.append({"type": "bind_off", "method": "gather"})
            elif re.match(r"^(?:Row|Rnd|Round)s?\b|^(?:Repeat|Rep|Work)\b", ln, re.I):
                warnings.append(f"could not read instruction line: {ln}")
        except (GrammarError, KeyError) as e:
            warnings.append(f"{ln[:60]} → {e}")

    if gauge is not None:
        gauge["needle_mm"] = needle_mm
    if cast_on is None:
        return ParseResult(pattern=None, warnings=warnings + ["no cast-on line found"])
    try:
        pattern = Pattern.model_validate({
            "title": title, "construction": construction, "sizes": sizes, "gauge": gauge,
            "pieces": [{"name": "body", "cast_on": cast_on, "steps": steps}]})
    except ValidationError as e:
        return ParseResult(pattern=None, warnings=warnings + [f"invalid IR: {e.errors()[0]['msg']}"])
    return ParseResult(pattern=pattern, warnings=warnings)
