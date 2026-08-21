"""
Candidate-level graph. Fans out across an arbitrary number of references
(REF1 or REF2, or a mix) using LangGraph's Send API, runs each through
the appropriate single-reference subgraph via CandidateNodes.run_reference,
then aggregates.

    START --> fan_out_references --[Send x N]--> run_reference (parallel)
                                                        |
                                                        v  (all N complete)
                                              cross_check_references
                                                        |
                                                        v
                                                 score_overall
                                                        |
                                          [cond: route_overall_review]
                                        /                              \
                        overall_flag_for_review                  overall_clear
                                        \                              /
                                                       END
"""

from typing import Optional

try:
    from langgraph.types import Send
except ImportError:
    from langgraph.constants import Send

from langgraph.graph import StateGraph, START, END

from refcheck.nodes.candidate_nodes import CandidateNodes
from refcheck.llm.base import BaseLLMProvider
from refcheck.schemas import REF_TYPE_OPEN_TEXT, REF_TYPE_YES_NO, CandidateState


def fan_out_references(state: CandidateState):
    """One Send per reference, carrying only the fields that reference's
    `type` (REF1/REF2) actually needs."""
    sends = []
    for ref in state["references"]:
        payload = {
            "candidate_name": state["candidate_name"],
            "role_applied_for": state["role_applied_for"],
            "claimed_details": state["claimed_details"],
            "reference_name": ref.reference_name,
            "relationship": ref.relationship,
            "type": ref.type,
        }
        if ref.type == REF_TYPE_OPEN_TEXT:
            payload["raw_input"] = ref.raw_input
        elif ref.type == REF_TYPE_YES_NO:
            payload["yes_no_form"] = ref.yes_no_form
        sends.append(Send("run_reference", payload))
    return sends


def build_candidate_graph(llm_provider: Optional[BaseLLMProvider] = None):
    nodes = CandidateNodes(llm_provider)
    graph = StateGraph(CandidateState)

    graph.add_node("run_reference", nodes.run_reference)
    graph.add_node("cross_check_references", nodes.cross_check_references)
    graph.add_node("score_overall", nodes.score_overall)
    graph.add_node("overall_flag_for_review", nodes.overall_flag_for_review)
    graph.add_node("overall_clear", nodes.overall_clear)

    graph.add_conditional_edges(START, fan_out_references, ["run_reference"])
    graph.add_edge("run_reference", "cross_check_references")
    graph.add_edge("cross_check_references", "score_overall")

    graph.add_conditional_edges(
        "score_overall", nodes.route_overall_review,
        {"overall_flag_for_review": "overall_flag_for_review", "overall_clear": "overall_clear"},
    )
    graph.add_edge("overall_flag_for_review", END)
    graph.add_edge("overall_clear", END)

    return graph.compile()


if __name__ == "__main__":
    from refcheck.llm.providers import get_provider
    app = build_candidate_graph(get_provider())
    print(app.get_graph().draw_mermaid())
