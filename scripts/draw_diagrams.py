"""Draw the report diagrams as PNG (matplotlib only, no external services).

  docs/diagrams/system.png      data flow: user → router → NLP components → code checks → data
  docs/diagrams/chat_graph.png  the LangGraph chat graph (nodes read from graph.ROUTES)
Run: python scripts/draw_diagrams.py
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "docs" / "diagrams"
RED, RED_SOFT = "#C8283C", "#F8E1E3"
GREEN, GREEN_SOFT = "#2E7D4F", "#E3F1E8"
SAND, SAND_SOFT = "#8C6A4F", "#F3EBE2"
INK, GREY = "#2E2522", "#7A6A62"


def box(ax, x, y, w, h, title, sub="", fc="#fff", ec=INK, bold=True):
    ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="round,pad=0.02,rounding_size=0.12",
                                fc=fc, ec=ec, lw=1.4))
    ax.text(x, y + (0.13 if sub else 0), title, ha="center", va="center", fontsize=10.5, color=INK,
            fontweight="bold" if bold else "normal")
    if sub:
        ax.text(x, y - 0.2, sub, ha="center", va="center", fontsize=8, color=GREY)


def arrow(ax, a, b, color=INK, style="-|>", rad=0.0, lw=1.2, ls="-"):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle=style, mutation_scale=11, color=color, lw=lw, ls=ls,
                                 connectionstyle=f"arc3,rad={rad}", shrinkA=2, shrinkB=2))


def group(ax, x0, y0, x1, y1, label, fc, ec):
    ax.add_patch(FancyBboxPatch((x0, y0), x1 - x0, y1 - y0, boxstyle="round,pad=0.02,rounding_size=0.2",
                                fc=fc, ec=ec, lw=1, ls="--", alpha=0.9))
    ax.text(x0 + 0.15, y1 - 0.22, label, fontsize=9.5, color=ec, fontweight="bold", va="top")


def system() -> None:
    from knit_copilot import kb
    from knit_copilot.components import yarn_linker
    fig, ax = plt.subplots(figsize=(15, 8.6))
    ax.set_xlim(0, 15)
    ax.set_ylim(0, 8.6)
    ax.axis("off")

    group(ax, 3.0, 0.75, 7.6, 8.3, "NLP components (LLM + checks)", RED_SOFT, RED)
    group(ax, 8.1, 0.75, 11.6, 8.3, "Code only (numbers, rules)", GREEN_SOFT, GREEN)
    group(ax, 12.1, 0.75, 14.8, 8.3, "Data", SAND_SOFT, SAND)

    box(ax, 1.3, 6.6, 2.0, 0.9, "Knitter", "chat · forms · pattern text", fc="#fff")
    box(ax, 1.3, 4.3, 2.0, 1.1, "Router", "rules → LLM\nintent classification", fc="#fff", ec=RED)

    rows = {"setup": 7.3, "parser": 6.1, "rewrite": 4.85, "explain": 3.6, "yarn": 2.35, "kb": 1.3}
    box(ax, 5.3, rows["setup"], 3.4, 0.9, "Setup agent", "LLM tool calls → project", ec=RED)
    box(ax, 5.3, rows["parser"], 3.4, 0.9, "Parser", "grammar → LLM (hybrid) · text → Pattern IR", ec=RED)
    box(ax, 5.3, rows["rewrite"], 3.4, 0.9, "Rewriter", "edit list (code) → LLM → re-parse", ec=RED)
    box(ax, 5.3, rows["explain"], 3.4, 0.9, "Explainer", "fact sheet → LLM → number/citation check", ec=RED)
    box(ax, 4.25, rows["yarn"], 1.9, 0.9, "Yarn linker", "entity linking", ec=RED)
    box(ax, 6.4, rows["yarn"], 1.9, 0.9, "Yarn advisor", "rules → LLM", ec=RED)
    box(ax, 5.3, rows["kb"], 3.4, 0.8, "KB retrieval", "exact · fuzzy · BM25 + dense (RRF)", ec=RED)

    code = {"project": (7.3, "Project rules", "setup → lock → start over"),
            "sim": (6.1, "Stitch simulator", "counts per row, markers"),
            "gauge": (4.85, "Gauge adjuster", "closest valid counts, repeats kept"),
            "chart": (3.6, "Chart builder", "matplotlib grid"),
            "tracker": (2.35, "Row tracker", "current row, stitch counts")}
    for k, (y, t, sub) in code.items():
        box(ax, 9.85, y, 3.0, 0.9, t, sub, ec=GREEN)

    box(ax, 13.45, 7.3, 2.3, 0.9, "SQLite", "projects, versions", ec=SAND)
    box(ax, 13.45, 6.1, 2.3, 0.9, "Abbreviation KB", f"{len(kb.abbreviations())} entries · fibres", ec=SAND)
    box(ax, 13.45, 2.35, 2.3, 0.9, "yarns.csv", f"{len(yarn_linker.yarns())} yarns (UA market)", ec=SAND)
    ax.text(13.45, 1.55, "read by the yarn linker\nand yarn advisor", ha="center", fontsize=7.5, color=SAND)
    ax.text(13.45, 5.3, "read by the parser, simulator,\nexplainer, charts, retrieval", ha="center",
            fontsize=7.5, color=SAND)

    arrow(ax, (1.3, 6.15), (1.3, 4.85))
    for k in ("setup", "parser", "explain", "kb"):
        arrow(ax, (2.3, 4.3), (3.6, rows[k]), color=GREY)
    arrow(ax, (2.3, 4.3), (3.3, rows["yarn"]), color=GREY)
    arrow(ax, (5.2, rows["yarn"]), (5.45, rows["yarn"]))
    arrow(ax, (7.0, 7.3), (8.35, 7.3), color=RED)                       # tool calls → project
    ax.text(7.68, 7.42, "tool calls", fontsize=7.5, color=RED, ha="center")
    arrow(ax, (7.0, 6.2), (8.35, 6.2), color=RED)                       # IR → simulator
    ax.text(7.68, 6.3, "IR", fontsize=7.5, color=RED, ha="center")
    arrow(ax, (8.35, 5.98), (7.0, 5.98), color=GREEN, ls="--")          # errors → repair
    ax.text(7.68, 5.72, "errors → repair", fontsize=7, color=GREEN, ha="center")
    arrow(ax, (8.35, 4.85), (7.0, 4.85), color=GREEN)                   # adjusted counts → rewriter
    ax.text(7.68, 4.95, "new counts", fontsize=7.5, color=GREEN, ha="center")
    arrow(ax, (5.3, 5.3), (5.3, 5.65), color=RED, ls="--")              # rewriter → parser (verify)
    ax.text(5.42, 5.47, "re-parse to verify", fontsize=7, color=RED, va="center")
    arrow(ax, (8.4, 5.7), (7.0, 3.75), color=GREEN, rad=0.15)           # simulator → explainer facts
    ax.text(7.8, 4.2, "facts", fontsize=7.5, color=GREEN)
    arrow(ax, (9.85, 6.85), (9.85, 6.55), color=GREEN)                  # project → simulate
    arrow(ax, (9.85, 6.85 - 1.25), (9.85, 5.3), color=GREEN)            # simulator → gauge
    arrow(ax, (12.3, 7.3), (11.35, 7.3), color=SAND, style="<|-|>")
    arrow(ax, (12.3, 6.1), (11.35, 6.1), color=SAND)

    ax.text(0.2, 0.3, "Every number shown to the user comes from code. LLM output that contains numbers is checked "
                      "(simulation, re-parse, fact sheet) before it is shown.", fontsize=9.5, color=INK)
    fig.tight_layout()
    fig.savefig(OUT / "system.png", dpi=160)
    plt.close(fig)


def chat_graph() -> None:
    from knit_copilot.graph import ROUTES
    nodes = sorted(set(ROUTES.values()), key=["setup", "adjust", "explain", "yarn", "lookup", "chart", "tracker",
                                               "validate", "other"].index)
    uses_llm = {"setup": "LLM tool calls", "explain": "LLM + check", "yarn": "linker + LLM", "adjust": "code",
                "lookup": "retrieval", "chart": "code", "tracker": "code", "validate": "code", "other": "fixed text"}
    intents = {n: [i for i, v in ROUTES.items() if v == n] for n in nodes}
    fig, ax = plt.subplots(figsize=(15, 5.2))
    ax.set_xlim(0, 15)
    ax.set_ylim(0, 5.2)
    ax.axis("off")
    box(ax, 1.0, 4.4, 1.2, 0.6, "START", fc="#fff")
    box(ax, 3.4, 4.4, 2.4, 0.8, "route", "rules → LLM", fc="#fff", ec=RED)
    box(ax, 13.8, 0.6, 1.2, 0.6, "END", fc="#fff")
    arrow(ax, (1.6, 4.4), (2.2, 4.4))
    xs = [0.9 + i * 1.55 for i in range(len(nodes))]
    for x, n in zip(xs, nodes):
        llm = uses_llm[n].startswith("LLM") or "LLM" in uses_llm[n]
        box(ax, x, 2.4, 1.4, 0.8, n, uses_llm[n], ec=RED if llm else GREEN)
        ax.text(x, 3.0, "\n".join(intents[n]), ha="center", va="bottom", fontsize=6.6, color=GREY)
        arrow(ax, (3.4, 4.0), (x, 2.82), color=GREY, lw=0.9)
        arrow(ax, (x, 1.98), (13.2, 0.65), color=GREY, lw=0.6)
    ax.text(5.0, 4.75, "LangGraph StateGraph · InMemorySaver checkpointer (thread = project) · every node writes a "
                       "trace record", fontsize=8.5, color=INK)
    fig.tight_layout()
    fig.savefig(OUT / "chat_graph.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    system()
    chat_graph()
    print("->", OUT / "system.png", OUT / "chat_graph.png")
