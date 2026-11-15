# Chat graph (LangGraph)

Generated from the code: `python -c "from knit_copilot import graph; print(graph.mermaid())"`.
Each node is a thin adapter around one component (see `src/knit_copilot/graph.py`).

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	route(route)
	setup(setup)
	adjust(adjust)
	explain(explain)
	yarn(yarn)
	lookup(lookup)
	chart(chart)
	tracker(tracker)
	validate(validate)
	other(other)
	__end__([<p>__end__</p>]):::last
	__start__ --> route;
	route -.-> adjust;
	route -.-> chart;
	route -.-> explain;
	route -.-> lookup;
	route -.-> other;
	route -.-> setup;
	route -.-> tracker;
	route -.-> validate;
	route -.-> yarn;
	adjust --> __end__;
	chart --> __end__;
	explain --> __end__;
	lookup --> __end__;
	other --> __end__;
	setup --> __end__;
	tracker --> __end__;
	validate --> __end__;
	yarn --> __end__;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc

```
