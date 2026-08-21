import graphviz

dot = graphviz.Digraph("business_flow", format="png")
dot.attr(rankdir="LR", splines="ortho", nodesep="0.6", ranksep="0.8",
         fontname="Helvetica", bgcolor="white")
dot.attr("node", fontname="Helvetica", fontsize="13")
dot.attr("edge", fontname="Helvetica", fontsize="11", color="#555555", penwidth="1.4")

STEP = {"shape": "box", "style": "rounded,filled", "fillcolor": "#DCE8FA",
        "color": "#5B84B1", "penwidth": "1.6", "fontsize": "13", "margin": "0.25,0.18"}
DECISION = {"shape": "diamond", "style": "filled", "fillcolor": "#FBE6C7",
            "color": "#C89B4A", "penwidth": "1.6", "fontsize": "12"}
GOOD = {"shape": "box", "style": "rounded,filled", "fillcolor": "#E4F2E4",
        "color": "#6FA36F", "penwidth": "1.6", "fontsize": "13", "margin": "0.25,0.18"}
FLAG = {"shape": "box", "style": "rounded,filled", "fillcolor": "#FADBD8",
        "color": "#C0605A", "penwidth": "1.6", "fontsize": "13", "margin": "0.25,0.18"}

dot.node("submit", "HR submits a\ncandidate + their\nreferences", **STEP)
dot.node("process", "System reads every\nreference automatically\n(calls, emails, or forms)", **STEP)
dot.node("compare", "Compares what each\nreference says against\nwhat the candidate claimed", **STEP)
dot.node("decide", "Anything doesn't\nmatch, or references\ndisagree with each other?", **DECISION)
dot.node("clear", "Clean report\ndelivered automatically\n(no delay)", **GOOD)
dot.node("flag", "Flagged for a\nhuman reviewer, with\nthe specific concern\nhighlighted", **FLAG)

dot.edge("submit", "process")
dot.edge("process", "compare")
dot.edge("compare", "decide")
dot.edge("decide", "clear", label="  no", fontcolor="#3C7A3C")
dot.edge("decide", "flag", label="  yes", fontcolor="#A0433D")

dot.render("/home/claude/refcheck-agent/docs/diagrams/business_flow", cleanup=True)
print("done")
