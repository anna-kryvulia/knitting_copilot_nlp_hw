"""Knitting charts (UC4): Pattern IR rows → chart grid → PNG.

Purpose: show the stitch structure as a standard chart (symbols from the abbreviation KB).
Input: Pattern IR, size, which rows (labels), mode (full width or one motif repeat).
Output: Chart (grid model, used by the eval) and `render_png()` bytes. Model calls: none.

Conventions:
- Row 1 at the bottom. RS rows and rounds are read right → left (row number on the right), WS rows left → right
  (number on the left); WS cells use the KB's WS symbol (a knit on the WS shows as a purl bump: •).
- One cell per stitch on the needle after the row; an op that makes n stitches spans n cells (cables, kfb);
  ops that make none (bind off, drop) and markers have no cell. Rows with fewer stitches are padded on the
  left with grey "no stitch" cells.
- Motif mode (automatic above MAX_FULL_WIDTH stitches): edge stitches + the first W stitches of the repeated
  region, W = the most common multi-stitch repeat block of the charted rows; the repeat is boxed in red.
"""

from __future__ import annotations

import io
import re
from collections import Counter

from pydantic import BaseModel

from knit_copilot import kb
from knit_copilot.ir import Item, Op, Pattern, Repeat, resolve
from knit_copilot.simulator import _static_consumption, simulate

MAX_FULL_WIDTH = 48


class Cell(BaseModel):
    op: str
    symbol: str
    width: int
    rep: int | None = None          # iteration of the row's top-level repeat (1-based), None outside repeats
    single: bool = False            # from a one-stitch repeat ("k to end", "p to last 2 sts")


class ChartRow(BaseModel):
    number: int                      # row/round number in the piece
    label: str
    side: str                        # RS | WS | round
    cells: list[Cell]                # in working order

    @property
    def width(self) -> int:
        return sum(c.width for c in self.cells)

    def display(self) -> list[Cell]:
        """Cells left → right as drawn."""
        return self.cells if self.side == "WS" else list(reversed(self.cells))


class Chart(BaseModel):
    title: str
    rows: list[ChartRow]             # worked order (bottom → top)
    width: int
    motif_mode: bool
    motif_width: int | None = None
    legend: dict[str, tuple[str, str]]   # op id -> (symbol, name)


def _cells(items: list[Item], rec: list, size: str | None, side: str, out: list[Cell],
           rep: int | None = None, top: bool = True, single: bool = False) -> None:
    """Chart cells for `items`, using the simulator's record `rec` for the real repeat counts."""
    for it, r in zip(items, rec):
        if isinstance(it, Op):
            a = kb.stitch_op(it.op)
            for _ in range(resolve(it.n, size)):
                if a.produces > 0:
                    sym = (a.chart_symbol_ws if side == "WS" else a.chart_symbol) or ""
                    out.append(Cell(op=a.id, symbol=sym, width=a.produces, rep=rep, single=single))
            continue
        one = top and len(it.repeat) == 1 and isinstance(it.repeat[0], Op)
        for i, inner in enumerate(r["iters"]):
            _cells(it.repeat, inner, size, side, out, rep=(i + 1) if top else rep, top=False,
                   single=one if top else single)


def _repeat_count(cells: list[Cell]) -> int | None:
    """Number of iterations of the row's multi-stitch repeat (e.g. 13 for (k6, k2tog) on 104 sts)."""
    reps = [c.rep for c in cells if c.rep is not None and not c.single]
    return max(reps) if reps else None


def _trim_to_motif(cells: list[Cell], n_repeats: int) -> list[Cell]:
    """Keep cells outside the repeat + one repeat: iteration 1 of a multi-stitch repeat, or for a one-stitch
    repeat ("p to last 2 sts") its width divided by the number of motif repeats."""
    single_width = sum(c.width for c in cells if c.single)
    keep_single = single_width // n_repeats if n_repeats and single_width % n_repeats == 0 else single_width
    out, taken = [], 0
    for c in cells:
        if c.rep is None:
            out.append(c)
        elif c.single:
            if taken < keep_single:
                out.append(c.model_copy(update={"rep": 1}))
                taken += c.width
        elif c.rep == 1:
            out.append(c)
    return out


def build(pattern: Pattern, size: str | None = None, labels: list[str] | None = None,
          motif: bool | None = None) -> Chart:
    """Chart the rows with `labels` (default: the most-repeated block of written rows)."""
    if size is None and pattern.sizes:
        size = pattern.sizes[0]
    sim = simulate(pattern, size)
    by_label = pattern.rows_by_label()
    if labels is None:
        labels = default_rows(pattern, size)
    first = {}
    for r in sim.rows:
        if r.label in labels and r.label not in first:
            first[r.label] = r
    picked = [(by_label[lb], first[lb].start_count, first[lb]) for lb in labels if lb in first and lb in by_label]
    rows: list[ChartRow] = []
    for row_ir, start, state in picked:
        cells: list[Cell] = []
        _cells(row_ir.ops, state.rec, size, state.side, cells)
        m = re.fullmatch(r"(?:Row|Rnd) (\d+)", state.label)     # chart rows use the pattern's row numbers
        rows.append(ChartRow(number=int(m.group(1)) if m else state.number, label=state.label, side=state.side,
                             cells=cells))
    full = max((r.width for r in rows), default=0)
    counts = [n for r in rows if (n := _repeat_count(r.cells))]
    n_rep = Counter(counts).most_common(1)[0][0] if counts else None
    use_motif = (full > MAX_FULL_WIDTH and n_rep is not None) if motif is None else (motif and n_rep is not None)
    w = None
    if use_motif:
        multi = [i for i, r in enumerate(rows) if _repeat_count(r.cells)]
        for r in rows:
            r.cells = _trim_to_motif(r.cells, n_rep)
        # rows made only of a one-stitch repeat that did not divide evenly ("k to end" incl. the edge stitches):
        # cut them to the width of the nearest motif row so the columns line up
        for i, r in enumerate(rows):
            if i not in multi and multi and all(c.single for c in r.cells):
                target = rows[min(multi, key=lambda j: abs(j - i))].width
                kept, total = [], 0
                for c in r.cells:
                    if total < target:
                        kept.append(c)
                        total += c.width
                r.cells = kept
        w = max(r.width for r in rows)
    legend = {}
    for r in rows:
        for c in r.cells:
            legend.setdefault(c.op if r.side != "WS" else f"{c.op}@WS",
                              (c.symbol, kb.abbreviations()[c.op].name + (" (on a WS row)" if r.side == "WS" else "")))
    return Chart(title=pattern.title, rows=rows, width=max((r.width for r in rows), default=0),
                 motif_mode=use_motif, motif_width=w if use_motif else None, legend=legend)


def default_rows(pattern: Pattern, size: str | None = None) -> list[str]:
    """Rows to chart by default: the block (a repeated group of rows, or a group of written rows) with the most
    stitch work (ops other than knit/purl), then the most distinct rows, then the most rows worked."""
    from knit_copilot.ir import RepeatRowsStep, RowsStep
    by_label = pattern.rows_by_label()
    sim = simulate(pattern, size)

    def work(labels: list[str]) -> int:
        def n(items):
            return sum(n(it.repeat) if isinstance(it, Repeat) else int(kb.stitch_op(it.op).id not in ("k", "p"))
                       for it in items)
        return sum(n(by_label[lb].ops) for lb in labels if lb in by_label)

    candidates = []
    for i, st in enumerate(pattern.pieces[0].steps):
        if isinstance(st, RepeatRowsStep):
            labels, worked = st.rows_ref, sum(1 for r in sim.rows if r.step == i)
        elif isinstance(st, RowsStep):
            labels, worked = [r.label for r in st.rows], len(st.rows)
        else:
            continue
        if worked:
            candidates.append((work(labels) > 0, len(labels), worked, labels))
    if not candidates:
        return []
    return max(candidates, key=lambda c: c[:3])[3][:24]


# ---------- rendering ----------

def render_png(chart: Chart, dpi: int = 110) -> bytes:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    n_rows, width = len(chart.rows), max(chart.width, 1)
    cell = 0.32
    fig_w = min(max(4.0, (width + 4) * cell), 18)
    legend_lines = len(chart.legend)
    fig_h = min(max(2.5, (n_rows + 2) * cell + 0.25 * legend_lines + 0.6), 24)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_xlim(-2, width + 2)
    ax.set_ylim(-0.5 - 0.55 * legend_lines - 0.6, n_rows + 0.8)
    ax.axis("off")
    ax.set_title(chart.title + (" — one repeat (red box)" if chart.motif_mode else ""), fontsize=10)

    rep_cols: list[tuple[int, int]] = []
    for y, row in enumerate(chart.rows):
        cells = row.display()
        x = width - row.width                       # pad on the left
        for gx in range(x):
            ax.add_patch(Rectangle((gx, y), 1, 1, facecolor="#cccccc", edgecolor="#999999", lw=0.5))
        rep_span = [None, None]
        for c in cells:
            ax.add_patch(Rectangle((x, y), c.width, 1, facecolor="white", edgecolor="#555555", lw=0.6))
            a = kb.abbreviations()[c.op]
            if a.category == "cable":            # diagonal across the crossed stitches
                x0, x1 = (x, x + c.width) if a.lean == "right" else (x + c.width, x)
                ax.plot([x0 + 0.1 * (1 if x1 > x0 else -1), x1 - 0.1 * (1 if x1 > x0 else -1)], [y + 0.15, y + 0.85],
                        color="black", lw=1.6)
            elif c.symbol.strip():
                ax.text(x + c.width / 2, y + 0.5, c.symbol, ha="center", va="center", fontsize=8)
            if c.rep == 1 and not c.single:
                rep_span[0] = x if rep_span[0] is None else min(rep_span[0], x)
                rep_span[1] = x + c.width if rep_span[1] is None else max(rep_span[1], x + c.width)
            x += c.width
        if rep_span[0] is not None:
            rep_cols.append(tuple(rep_span))
        side_x = width + 0.3 if row.side in ("RS", "round") else -0.3
        ax.text(side_x, y + 0.5, str(row.number), ha="left" if row.side in ("RS", "round") else "right",
                va="center", fontsize=7)
    if rep_cols and n_rows and (chart.motif_mode or len(set(rep_cols)) == 1):
        x0, x1 = min(a for a, _ in rep_cols), max(b for _, b in rep_cols)      # union of the repeat columns
        ax.add_patch(Rectangle((x0, 0), x1 - x0, n_rows, fill=False, edgecolor="red", lw=1.6))
    # legend
    y = -0.9
    for key, (sym, name) in chart.legend.items():
        op = key.split("@")[0]
        ax.add_patch(Rectangle((0, y - 0.4), 1, 0.8, facecolor="white", edgecolor="#555555", lw=0.6))
        if kb.abbreviations()[op].category == "cable":
            lx = (0.15, 0.85) if kb.abbreviations()[op].lean == "right" else (0.85, 0.15)
            ax.plot(list(lx), [y - 0.3, y + 0.3], color="black", lw=1.4)
            sym_text = op.upper()
        else:
            ax.text(0.5, y, sym, ha="center", va="center", fontsize=8)
            sym_text = op
        ax.text(1.4, y, f"{sym_text}: {name}", va="center", fontsize=7)
        y -= 0.55
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()
