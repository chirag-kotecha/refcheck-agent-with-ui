import graphviz

dot = graphviz.Digraph("architecture", format="png")
dot.attr(rankdir="TB", splines="ortho", nodesep="0.45", ranksep="0.5",
         fontname="Helvetica", bgcolor="white")
dot.attr("node", fontname="Helvetica", fontsize="11")
dot.attr("edge", fontname="Helvetica", fontsize="9", color="#555555")

CLIENT = {"shape": "box", "style": "rounded,filled", "fillcolor": "#F0E4F7",
          "color": "#9B6FB0", "penwidth": "1.4"}
API_NODE = {"shape": "box", "style": "rounded,filled", "fillcolor": "#FBE6C7",
            "color": "#C89B4A", "penwidth": "1.4"}
CORE = {"shape": "box", "style": "rounded,filled", "fillcolor": "#E4F2E4",
        "color": "#6FA36F", "penwidth": "1.4"}
PROVIDER = {"shape": "box", "style": "rounded,filled", "fillcolor": "#DCE8FA",
            "color": "#5B84B1", "penwidth": "1.4"}
EXTERNAL = {"shape": "box", "style": "filled", "fillcolor": "#EDEDED", "color": "#888888"}

# Clients
dot.node("streamlit", "Streamlit UI\n(streamlit_app.py)", **CLIENT)
dot.node("external_caller", "External caller\n(any HTTP client)", **CLIENT)
dot.node("cli", "CLI scripts\n(run_demo*.py)", **CLIENT)

# API layer
dot.node("api", "FastAPI service (refcheck/api)\nPOST /checks   GET /checks/{id}\nasync job store + optional webhook", **API_NODE)

# Core pipeline
dot.node("graphs", "Graphs (refcheck/graphs)\nREF1 graph + REF2 graph +\ncandidate fan-out graph", **CORE)
dot.node("nodes", "Nodes (refcheck/nodes)\nReferenceCheckNodes + CandidateNodes\n(business logic, provider-agnostic)", **CORE)
dot.node("batch", "Batch pipeline (refcheck/pipelines)\nsame nodes, phased for bulk/offline runs", **CORE)

# Provider abstraction
dot.node("base", "BaseLLMProvider (refcheck/llm/base.py)\nretry, timeout, structured output, logging", **PROVIDER)
dot.node("anthropic_p", "AnthropicProvider", **PROVIDER)
dot.node("bedrock_p", "BedrockProvider", **PROVIDER)
dot.node("openrouter_p", "OpenRouterProvider", **PROVIDER)

# External services
dot.node("anthropic_api", "Anthropic API", **EXTERNAL)
dot.node("bedrock_api", "AWS Bedrock", **EXTERNAL)
dot.node("openrouter_api", "OpenRouter", **EXTERNAL)

dot.edge("streamlit", "api", label="HTTP")
dot.edge("external_caller", "api", label="HTTP")
dot.edge("cli", "graphs", label="direct call")

dot.edge("api", "graphs")
dot.edge("graphs", "nodes")
dot.edge("batch", "nodes", label="reuses same\nbusiness logic")
dot.edge("nodes", "base")

dot.edge("base", "anthropic_p", style="dashed", label="subclass")
dot.edge("base", "bedrock_p", style="dashed", label="subclass")
dot.edge("base", "openrouter_p", style="dashed", label="subclass")

dot.edge("anthropic_p", "anthropic_api")
dot.edge("bedrock_p", "bedrock_api")
dot.edge("openrouter_p", "openrouter_api")
dot.edge("batch", "anthropic_api", label="Batch API", style="dotted")
dot.edge("batch", "bedrock_api", label="Batch inference\n(S3-based)", style="dotted")

dot.render("/home/claude/refcheck-agent/docs/diagrams/architecture", cleanup=True)
print("done")
