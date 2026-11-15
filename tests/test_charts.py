from knit_copilot import charts
from knit_copilot.parser_grammar import parse

LACE = """Lace
CO 14 sts.
Row 1 (RS): K2, *yo, k2tog, k3; rep from * to last 2 sts, k2.
Row 2 (WS): K2, p to last 2 sts, k2.
Repeat Rows 1 and 2 3 more times.
BO all sts.
"""


def test_cells_direction_and_ws_symbols():
    ch = charts.build(parse(LACE).pattern)
    rs, ws = ch.rows
    assert [c.op for c in rs.cells][:4] == ["k", "k", "yo", "k2tog"] and rs.width == 14
    assert rs.display()[-1] is rs.cells[0]                 # RS read right to left
    assert ws.display()[0] is ws.cells[0] and ws.cells[0].symbol == "•"   # knit on WS shows as purl bump
    assert [r.number for r in ch.rows] == [1, 2]


def test_motif_mode_keeps_one_repeat_and_edges():
    ch = charts.build(parse(LACE).pattern, motif=True)
    assert [r.width for r in ch.rows] == [9, 9]            # k2 + one 5-st repeat + k2
    assert charts.render_png(ch)[:4] == b"\x89PNG"
