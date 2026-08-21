import graphviz

dot = graphviz.Digraph("candidate_graph", format="png")
dot.attr(rankdir="TB", splines="ortho", nodesep="0.5", ranksep="0.55",
         fontname="Helvetica", bgcolor="white")
dot.attr("node", fontname="Helvetica", fontsize="11")
dot.attr("edge", fontname="Helvetica", fontsize="9", color="#555555")

PY_NODE = {"shape": "box", "style": "rounded,filled", "fillcolor": "#E4F2E4",
           "color": "#6FA36F", "penwidth": "1.2"}
LLM_NODE = {"shape": "box", "style": "rounded,filled", "fillcolor": "#DCE8FA",
            "color": "#5B84B1", "penwidth": "1.2"}
COND_NODE = {"shape": "diamond", "style": "filled", "fillcolor": "#FBE6C7",
             "color": "#C89B4A", "penwidth": "1.2", "fontsize": "10"}
TERMINAL = {"shape": "ellipse", "style": "filled", "fillcolor": "#EDEDED", "color": "#888888"}
SUBGRAPH_NODE = {"shape": "box3d", "style": "filled", "fillcolor": "#F0E4F7",
                  "color": "#9B6FB0", "penwidth": "1.4"}

dot.node("start", "START\n(candidate + list of references,\neach REF1 or REF2)", **TERMINAL)
dot.node("fanout", "fan_out_references\n(python -- one Send per reference,\nregardless of type or count)", **PY_NODE)

dot.node("ref1", "run_reference\n(Reference A -- REF1)", **SUBGRAPH_NODE)
dot.node("ref2", "run_reference\n(Reference B -- REF2)", **SUBGRAPH_NODE)
dot.node("refN", "run_reference\n(Reference N -- either type)", **SUBGRAPH_NODE)

dot.node("cross", "cross_check_references\n(python -- do references disagree\nwith EACH OTHER, not just the candidate?)", **PY_NODE)
dot.node("score", "score_overall\n(python -- average confidence,\npenalized for disagreement)", **PY_NODE)
dot.node("cond", "overall\nreview needed?", **COND_NODE)
dot.node("flag", "overall_flag_for_review\n(LLM)", **LLM_NODE)
dot.node("clear", "overall_clear\n(LLM)", **LLM_NODE)
dot.node("end", "END\n(full report: per-reference results +\ncross-reference flags + overall verdict)", **TERMINAL)

dot.edge("start", "fanout")
dot.edge("fanout", "ref1", label="parallel")
dot.edge("fanout", "ref2", label="parallel")
dot.edge("fanout", "refN", label="parallel")
dot.edge("ref1", "cross")
dot.edge("ref2", "cross")
dot.edge("refN", "cross")
dot.edge("cross", "score")
dot.edge("score", "cond")
dot.edge("cond", "flag", label="conflict / low\navg confidence")
dot.edge("cond", "clear", label="consistent")
dot.edge("flag", "end")
dot.edge("clear", "end")

dot.render("/home/claude/refcheck-agent/docs/diagrams/candidate_graph", cleanup=True)
print("done")
