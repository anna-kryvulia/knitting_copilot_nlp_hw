"""Pattern templates for the synthetic generator: each returns a gold Pattern IR with random parameters.

Purpose: gold labels for the parser, explainer, charts, tracker and gauge evals come from these IRs
(and the simulator), never from an LLM. Every template is checked by simulation in the generator.
Input: random.Random. Output: knit_copilot.ir.Pattern (metric units).
"""

import random

from knit_copilot.ir import Pattern

ALL = "__all__"  # marker for "work this op to the end of the row"


# ---------- tiny builders ----------

def op(name: str, n=1) -> dict:
    return {"op": name, "n": n} if n != 1 else {"op": name}


def to_end(name: str, remaining=0) -> dict:
    """'k to end' / 'p to last 2 sts' as a single-op repeat."""
    return {"repeat": [op(name)], "until": {"remaining": remaining}}


def rep(items: list[dict], times=None, remaining=None) -> dict:
    if times is not None:
        return {"repeat": items, "times": times}
    return {"repeat": items, "until": {"remaining": remaining or 0}}


def row(label: str, side: str, ops: list[dict], stated=None) -> dict:
    r = {"label": label, "side": side, "ops": ops}
    if stated is not None:
        r["stated_count"] = stated
    return r


def rows(*rs: dict) -> dict:
    return {"type": "rows", "rows": list(rs)}


def repeat_rows(labels: list[str], times=None, length=None, count=None, measured_from="cast_on") -> dict:
    s = {"type": "repeat_rows", "rows_ref": labels, "measured_from": measured_from}
    if times is not None:
        s["times"] = times
    elif length is not None:
        s["until_length_cm"] = length
    else:
        s["until_count"] = count
    return s


def bind_off(method="standard") -> dict:
    return {"type": "bind_off", "method": method}


def pattern(title, construction, cast_on, steps, gauge, sizes=None) -> Pattern:
    return Pattern.model_validate({
        "title": title, "construction": construction, "sizes": sizes or [],
        "gauge": gauge, "pieces": [{"name": "body", "cast_on": cast_on, "steps": steps}]})


def gauge(rng: random.Random, sts: tuple[int, int], rows_per_st: float, needle: float, stitch: str) -> dict:
    s = rng.randint(*sts)
    return {"sts_per_10cm": s, "rows_per_10cm": round(s * rows_per_st), "needle_mm": needle, "stitch_pattern": stitch}


# ---------- templates ----------

def garter_scarf(rng: random.Random) -> Pattern:
    n = rng.randint(24, 40)
    return pattern("Garter Stitch Scarf", "flat", n, [
        rows(row("Row 1", "RS", [to_end("k")]), row("Row 2", "WS", [to_end("k")])),
        repeat_rows(["Row 1", "Row 2"], length=rng.choice([120, 140, 150, 160])),
        bind_off("loose")],
        gauge(rng, (16, 20), 2.0, rng.choice([5.0, 5.5]), "garter"))


def rib_scarf(rng: random.Random) -> Pattern:
    m = rng.randint(6, 9)
    n = 4 * m + 2
    return pattern("2x2 Ribbed Scarf", "flat", n, [
        rows(row("Row 1", "RS", [op("k", 2), rep([op("p", 2), op("k", 2)], remaining=0)]),
             row("Row 2", "WS", [op("p", 2), rep([op("k", 2), op("p", 2)], remaining=0)])),
        repeat_rows(["Row 1", "Row 2"], length=rng.choice([130, 150, 160])),
        bind_off("in pattern")],
        gauge(rng, (20, 24), 1.4, 4.0, "2x2 rib, unstretched"))


def seed_cowl(rng: random.Random) -> Pattern:
    n = 2 * rng.randint(40, 60)
    return pattern("Seed Stitch Cowl", "round", n, [
        rows(row("Rnd 1", "round", [rep([op("k"), op("p")], remaining=0)]),
             row("Rnd 2", "round", [rep([op("p"), op("k")], remaining=0)])),
        repeat_rows(["Rnd 1", "Rnd 2"], length=rng.choice([20, 25, 30])),
        bind_off("in pattern")],
        gauge(rng, (14, 18), 1.4, rng.choice([6.0, 6.5]), "seed stitch"))


def ribbed_hat(rng: random.Random) -> Pattern:
    """Multi-size hat in the round: 2x2 rib brim, stockinette body, 8-section crown."""
    sizes = ["S", "M", "L"]
    base = rng.choice([80, 88])
    co = {s: base + 8 * i for i, s in enumerate(sizes)}
    body = {s: 15 + 2 * i for i, s in enumerate(sizes)}
    crown = []
    for k in range(6, 0, -1):                      # *k6, k2tog* ... *k1, k2tog*
        crown.append(row(f"Rnd {len(crown) + 3}", "round", [rep([op("k", k), op("k2tog")], remaining=0)],
                         stated={s: co[s] // 8 * (k + 1) for s in sizes}))
        crown.append(row(f"Rnd {len(crown) + 3}", "round", [to_end("k")]))
    crown.append(row(f"Rnd {len(crown) + 3}", "round", [rep([op("k2tog")], remaining=0)],
                     stated={s: co[s] // 8 for s in sizes}))
    return pattern("Ribbed Beanie", "round", co, [
        rows(row("Rnd 1", "round", [rep([op("k", 2), op("p", 2)], remaining=0)])),
        repeat_rows(["Rnd 1"], length=rng.choice([5, 6])),
        rows(row("Rnd 2", "round", [to_end("k")])),
        repeat_rows(["Rnd 2"], length=body),
        rows(*crown),
        bind_off("gather")],
        gauge(rng, (20, 22), 1.35, 4.0, "stockinette"), sizes)


def eyelet_scarf(rng: random.Random) -> Pattern:
    m = rng.randint(5, 8)
    n = 5 * m + 4
    edge = [op("k", 2)]
    return pattern("Eyelet Lace Scarf", "flat", n, [
        rows(row("Border row", "RS", [to_end("k")])),
        repeat_rows(["Border row"], times=3),
        rows(row("Row 1", "RS", edge + [rep([op("yo"), op("k2tog"), op("k", 3)], remaining=2)] + edge, stated=n),
             row("Row 2", "WS", edge + [to_end("p", remaining=2)] + edge),
             row("Row 3", "RS", edge + [rep([op("k", 3), op("yo"), op("ssk")], remaining=2)] + edge),
             row("Row 4", "WS", edge + [to_end("p", remaining=2)] + edge)),
        repeat_rows(["Row 1", "Row 2", "Row 3", "Row 4"], length=rng.choice([140, 150, 160])),
        rows(row("Final border row", "RS", [to_end("k")])),
        repeat_rows(["Final border row"], times=3),
        bind_off("loose")],
        gauge(rng, (18, 22), 1.4, rng.choice([4.0, 4.5]), "eyelet pattern, blocked"))


def feather_fan(rng: random.Random) -> Pattern:
    m = rng.randint(2, 4)
    n = 18 * m + 2
    fan = [rep([op("k2tog")], times=3), rep([op("yo"), op("k")], times=6), rep([op("k2tog")], times=3)]
    return pattern("Feather and Fan Wrap", "flat", n, [
        rows(row("Row 1", "RS", [to_end("k")]),
             row("Row 2", "WS", [to_end("p")]),
             row("Row 3", "RS", [op("k"), rep(fan, remaining=1), op("k")], stated=n),
             row("Row 4", "WS", [to_end("k")])),
        repeat_rows(["Row 1", "Row 2", "Row 3", "Row 4"], length=rng.choice([150, 160, 170])),
        bind_off("loose")],
        gauge(rng, (18, 21), 1.3, rng.choice([4.5, 5.0]), "feather and fan, blocked"))


def cable_scarf(rng: random.Random) -> Pattern:
    m = rng.randint(2, 3)
    n = 8 + 8 * m
    cable = rng.choice(["c6b", "c6f"])
    rs_plain = [op("k", 3), rep([op("p", 2), op("k", 6)], times=m), op("p", 2), op("k", 3)]
    rs_cable = [op("k", 3), rep([op("p", 2), op(cable)], times=m), op("p", 2), op("k", 3)]
    ws = [op("k", 3), op("k", 2), rep([op("p", 6), op("k", 2)], times=m), op("k", 3)]
    return pattern("Cabled Scarf", "flat", n, [
        rows(row("Row 1", "RS", rs_plain), row("Row 2", "WS", ws),
             row("Row 3", "RS", rs_plain), row("Row 4", "WS", ws),
             row("Row 5", "RS", rs_cable), row("Row 6", "WS", ws),
             row("Row 7", "RS", rs_plain), row("Row 8", "WS", ws)),
        repeat_rows([f"Row {i}" for i in range(1, 9)], length=rng.choice([140, 150])),
        bind_off("in pattern")],
        gauge(rng, (22, 26), 1.3, rng.choice([4.0, 4.5]), "cable pattern"))


def bias_dishcloth(rng: random.Random) -> Pattern:
    top = rng.choice([36, 40, 44, 48])
    return pattern("Bias Dishcloth", "flat", 4, [
        rows(row("Row 1", "RS", [to_end("k")])),
        rows(row("Inc row", "RS", [op("k", 2), op("yo"), to_end("k")])),
        repeat_rows(["Inc row"], count=top),
        rows(row("Dec row", "RS", [op("k"), op("k2tog"), op("yo"), op("k2tog"), to_end("k")])),
        repeat_rows(["Dec row"], count=4),
        bind_off()],
        gauge(rng, (16, 18), 2.0, 4.5, "garter"))


def bordered_blanket(rng: random.Random) -> Pattern:
    sizes = ["Stroller", "Crib"]
    co = {"Stroller": rng.choice([100, 110]), "Crib": rng.choice([130, 140])}
    length = {"Stroller": 75, "Crib": 100}
    border = rng.choice([5, 6])
    return pattern("Garter-Bordered Baby Blanket", "flat", co, [
        rows(row("Border row", "RS", [to_end("k")])),
        repeat_rows(["Border row"], times=2 * border - 1),
        rows(row("Row 1", "RS", [to_end("k")]),
             row("Row 2", "WS", [op("k", border), to_end("p", remaining=border), op("k", border)])),
        repeat_rows(["Row 1", "Row 2"], length=length),
        rows(row("Top border row", "RS", [to_end("k")])),
        repeat_rows(["Top border row"], times=2 * border - 1),
        bind_off("loose")],
        gauge(rng, (16, 18), 1.4, 5.0, "stockinette"), sizes)


TEMPLATES = {
    "garter_scarf": garter_scarf, "rib_scarf": rib_scarf, "seed_cowl": seed_cowl, "ribbed_hat": ribbed_hat,
    "eyelet_scarf": eyelet_scarf, "feather_fan": feather_fan, "cable_scarf": cable_scarf,
    "bias_dishcloth": bias_dishcloth, "bordered_blanket": bordered_blanket,
}


# ---------- templates with stitch markers (added for real-pattern features, separate eval file) ----------

def to_marker(name: str, remaining=0) -> dict:
    return {"repeat": [op(name)], "until": {"remaining": remaining, "marker": True}}


def marker_hat(rng: random.Random) -> Pattern:
    """Hat in the round with 8 crown sections marked by stitch markers: 'k to 2 sts before marker, k2tog, sm'."""
    sizes = ["S", "M", "L"]
    sec = {"S": 10, "M": 11, "L": 12}
    co = {s: 8 * n for s, n in sec.items()}
    body = {s: 14 + i for i, s in enumerate(sizes)}
    return pattern("Sectioned Beanie", "round", co, [
        rows(row("Rnd 1", "round", [rep([op("k", 2), op("p", 2)], remaining=0)])),
        repeat_rows(["Rnd 1"], length=rng.choice([4, 5])),
        rows(row("Rnd 2", "round", [to_end("k")])),
        repeat_rows(["Rnd 2"], length=body),
        rows(row("Set-up rnd", "round", [rep([op("k", sec), op("pm")], times=7), op("k", sec)]),
             row("Dec rnd", "round", [rep([to_marker("k", 2), op("k2tog"), op("sm")], remaining=0)],
                 stated={s: co[s] - 8 for s in sizes}),
             row("Knit rnd", "round", [to_end("k")])),
        repeat_rows(["Dec rnd", "Knit rnd"], count=40),
        repeat_rows(["Dec rnd"], count=16),
        rows(row("Last rnd", "round", [rep([op("k2tog")], remaining=0)], stated=8)),
        bind_off("gather")],
        gauge(rng, (20, 22), 1.35, 4.0, "stockinette"), sizes)


def triangle_shawl(rng: random.Random) -> Pattern:
    """Top-down triangle shawl with a centre stitch between two markers; 4 increases every RS row."""
    top = 7 + 4 * rng.randint(20, 35)
    return pattern("Centre-Out Triangle Shawl", "flat", 5, [
        rows(row("Row 1", "RS", [op("k", 2), op("yo"), op("pm"), op("k"), op("pm"), op("yo"), op("k", 2)], stated=7),
             row("Row 2", "WS", [op("k", 2), to_end("p", 2), op("k", 2)]),
             row("Row 3", "RS", [op("k", 2), op("yo"), to_marker("k"), op("yo"), op("sm"), op("k"), op("sm"), op("yo"),
                                 to_end("k", 2), op("yo"), op("k", 2)], stated=11),
             row("Row 4", "WS", [op("k", 2), to_end("p", 2), op("k", 2)])),
        repeat_rows(["Row 3", "Row 4"], count=top),
        rows(row("Edge row 1", "RS", [to_end("k")])),
        repeat_rows(["Edge row 1"], times=3),
        bind_off("loose")],
        gauge(rng, (18, 22), 1.4, rng.choice([4.0, 4.5]), "garter-edged stockinette"))


MARKER_TEMPLATES = {"marker_hat": marker_hat, "triangle_shawl": triangle_shawl}
