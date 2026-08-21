import graphviz

dot = graphviz.Digraph("reference_graphs", format="png")
dot.attr(rankdir="TB", splines="ortho", nodesep="0.4", ranksep="0.5",
         fontname="Helvetica", bgcolor="white")
dot.attr("node", fontname="Helvetica", fontsize="11")
dot.attr("edge", fontname="Helvetica", fontsize="9", color="#555555")

LLM_NODE = {"shape": "box", "style": "rounded,filled", "fillcolor": "#DCE8FA",
            "color": "#5B84B1", "penwidth": "1.2"}
PY_NODE = {"shape": "box", "style": "rounded,filled", "fillcolor": "#E4F2E4",
           "color": "#6FA36F", "penwidth": "1.2"}
COND_NODE = {"shape": "diamond", "style": "filled", "fillcolor": "#FBE6C7",
             "color": "#C89B4A", "penwidth": "1.2", "fontsize": "10"}
TERMINAL = {"shape": "ellipse", "style": "filled", "fillcolor": "#EDEDED", "color": "#888888"}

with dot.subgraph(name="cluster_ref1") as c:
    c.attr(label="REF1 -- Open-Text Reference (transcript / email)", fontsize="14",
           fontname="Helvetica-Bold", style="rounded,dashed", color="#666666",
           labelloc="t", margin="20")
    c.node("r1_start", "START", **TERMINAL)
    c.node("r1_extract", "extract_facts\n(LLM -- extraction tier)", **LLM_NODE)
    c.node("r1_sentiment", "sentiment_and_redflags\n(LLM -- extraction tier)", **LLM_NODE)
    c.node("r1_diff", "diff_facts\n(python)", **PY_NODE)
    c.node("r1_cond1", "discrepancies\nfound?", **COND_NODE)
    c.node("r1_explain", "explain_discrepancies\n(LLM -- reasoning tier)", **LLM_NODE)
    c.node("r1_score", "score_confidence\n(python)", **PY_NODE)
    c.node("r1_cond2", "route\nreview?", **COND_NODE)
    c.node("r1_flag", "flag_for_human_review\n(LLM)", **LLM_NODE)
    c.node("r1_auto", "auto_summarize\n(LLM)", **LLM_NODE)
    c.node("r1_end", "END", **TERMINAL)

    c.edge("r1_start", "r1_extract")
    c.edge("r1_start", "r1_sentiment")
    c.edge("r1_extract", "r1_diff")
    c.edge("r1_sentiment", "r1_diff")
    c.edge("r1_diff", "r1_cond1")
    c.edge("r1_cond1", "r1_explain", label="yes")
    c.edge("r1_cond1", "r1_score", label="no")
    c.edge("r1_explain", "r1_score")
    c.edge("r1_score", "r1_cond2")
    c.edge("r1_cond2", "r1_flag", label="needs review")
    c.edge("r1_cond2", "r1_auto", label="clean")
    c.edge("r1_flag", "r1_end")
    c.edge("r1_auto", "r1_end")

with dot.subgraph(name="cluster_ref2") as c:
    c.attr(label="REF2 -- Yes/No Verification Form", fontsize="14",
           fontname="Helvetica-Bold", style="rounded,dashed", color="#666666",
           labelloc="t", margin="20")
    c.node("r2_start", "START", **TERMINAL)
    c.node("r2_eval", "evaluate_yes_no_form\n(python -- answers ARE the facts)", **PY_NODE)
    c.node("r2_cond1", "comments\nprovided?", **COND_NODE)
    c.node("r2_sentiment", "sentiment_from_comments\n(LLM -- extraction tier,\nsame prompt as REF1)", **LLM_NODE)
    c.node("r2_score", "score_confidence\n(python -- SAME method as REF1)", **PY_NODE)
    c.node("r2_cond2", "route\nreview?", **COND_NODE)
    c.node("r2_flag", "flag_for_human_review\n(LLM -- SAME method as REF1)", **LLM_NODE)
    c.node("r2_auto", "auto_summarize\n(LLM -- SAME method as REF1)", **LLM_NODE)
    c.node("r2_end", "END", **TERMINAL)

    c.edge("r2_start", "r2_eval")
    c.edge("r2_eval", "r2_cond1")
    c.edge("r2_cond1", "r2_sentiment", label="yes")
    c.edge("r2_cond1", "r2_score", label="no")
    c.edge("r2_sentiment", "r2_score")
    c.edge("r2_score", "r2_cond2")
    c.edge("r2_cond2", "r2_flag", label="needs review")
    c.edge("r2_cond2", "r2_auto", label="clean")
    c.edge("r2_flag", "r2_end")
    c.edge("r2_auto", "r2_end")

dot.render("/home/claude/refcheck-agent/docs/diagrams/reference_graphs", cleanup=True)
print("done")
