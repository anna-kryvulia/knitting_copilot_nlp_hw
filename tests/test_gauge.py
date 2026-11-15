"""Gauge adjustment checked against hand calculations."""
from knit_copilot.gauge import KnitterGauge, adjust, flatten_size, motifs
from knit_copilot.parser_grammar import parse
from knit_copilot.simulator import simulate

HAT = """Hat
Sizes: S (M)
Needles: 4 mm
Gauge: 21 sts and 28 rows = 10 cm in stockinette.
CO 88 (96) sts.
Join to work in the round.
Rnd 1: *k2, p2; rep from * to end.
Repeat Rnd 1 until work measures 5 cm from cast-on edge.
Rnd 2: *k6, k2tog; rep from * to end.
BO all sts.
"""

RIB = """Rib
Gauge: 22 sts and 30 rows = 10 cm in rib.
CO 30 sts.
Row 1 (RS): K2, *p2, k2; rep from * to end.
Row 2 (WS): P2, *k2, p2; rep from * to end.
Repeat Rows 1 and 2 until piece measures 10 cm from cast-on edge.
BO all sts.
"""

CABLE = """Cable
Gauge: 24 sts and 32 rows = 10 cm in cable pattern.
CO 24 sts.
Row 1 (RS): K3, (p2, k6) 2 times, p2, k3.
Row 2 (WS): K3, k2, (p6, k2) 2 times, k3.
Repeat Rows 1 and 2 4 more times.
BO all sts.
"""


def test_hat_closest_multiple_of_8():
    # target 88 x 18/21 = 75.43; rib needs a multiple of 4 and the crown a multiple of 8 -> 72 (3.43 away) beats 80
    a = adjust(parse(HAT).pattern, "S", KnitterGauge(sts_per_10cm=18, rows_per_10cm=24))
    assert a.ok and a.chosen_stitches == 72 and abs(a.target_stitches - 75.43) < 0.01
    assert a.before.width_cm == 41.9 and a.after.width_cm == 40.0
    assert simulate(a.pattern).rows[-2].end_count == 63           # 72 / 8 x 7


def test_size_is_flattened():
    a = adjust(parse(HAT).pattern, "M", KnitterGauge(sts_per_10cm=21, rows_per_10cm=28))
    assert a.chosen_stitches == 96 and a.pattern.sizes == []


def test_rib_keeps_4n_plus_2_and_length_in_cm():
    # target 30 x 20/22 = 27.27; valid counts 4n+2 -> 26 (1.27 away) beats 30
    a = adjust(parse(RIB).pattern, None, KnitterGauge(sts_per_10cm=20, rows_per_10cm=20))
    assert a.chosen_stitches == 26
    assert a.after.rows == 20 and a.after.length_cm == 10.0       # 10 cm at 20 rows/10 cm


def test_cable_repeat_count_is_resolved_and_motifs_kept():
    # target 24 x 30/24 = 30; valid 8 + 8m -> 32 (m = 3) beats 24
    p = parse(CABLE).pattern
    a = adjust(p, None, KnitterGauge(sts_per_10cm=30, rows_per_10cm=40))
    assert a.chosen_stitches == 32
    assert any(c.what.startswith("Row 1") and (c.old, c.new) == (2, 3) for c in a.changes)
    assert motifs(flatten_size(p, None)) == motifs(a.pattern)
    # fixed row repeats scale with rows: 5 passes x 40/32 = 6.25 -> 6 passes = 5 more
    assert any(c.what.startswith("repeat Row 1") and (c.old, c.new) == (4, 5) for c in a.changes)


def test_large_motif_gives_a_note():
    a = adjust(parse(CABLE).pattern, None, KnitterGauge(sts_per_10cm=27, rows_per_10cm=32))
    assert a.chosen_stitches == 24 and any("steps of" in n for n in a.notes)
