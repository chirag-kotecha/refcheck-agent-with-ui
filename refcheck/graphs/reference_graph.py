"""
Builds the two single-reference StateGraphs: REF1 (open text) and REF2
(yes/no form). Both built from the SAME ReferenceCheckNodes instance so
provider selection and shared logic (score_confidence, route_review)
only exist in one place.

REF1 shape:
    START -> extract_facts ---------\
      \                              +--> diff_facts -[cond]-> explain_discrepancies -> score_confidence
       \-> sentiment_and_redflags --/                   \                                     |
                                                           \-----------------------------------/
                                                                                                |
                                                                                    [cond: route_review]
                                                                    flag_for_human_review <-> auto_summarize -> END

REF2 shape (no extract_facts -- the form's answers ARE the facts):
    START -> evaluate_yes_no_form -[cond: has_comments]-> sentiment_from_comments -> score_confidence
                                \--------------------------------------------------------/
                                                                                          |
                                                                              [cond: route_review]
                                                              flag_for_human_review <-> auto_summarize -> END
"""

from typing import Optional

from langgraph.graph import StateGraph, START, END

from refcheck.llm.base import BaseLLMProvider
from refcheck.nodes.reference_nodes import ReferenceCheckNodes
from refcheck.schemas import ReferenceCheckState


def build_open_ended_graph(nodes: ReferenceCheckNodes):
    graph = StateGraph(ReferenceCheckState)

    graph.add_node("extract_facts", nodes.extract_facts)
    graph.add_node("sentiment_and_redflags", nodes.sentiment_and_redflags)
    graph.add_node("diff_facts", nodes.diff_facts)
    graph.add_node("explain_discrepancies", nodes.explain_discrepancies)
    graph.add_node("score_confidence", nodes.score_confidence)
    graph.add_node("flag_for_human_review", nodes.flag_for_human_review)
    graph.add_node("auto_summarize", nodes.auto_summarize)

    graph.add_edge(START, "extract_facts")
    graph.add_edge(START, "sentiment_and_redflags")
    graph.add_edge("extract_facts", "diff_facts")
    graph.add_edge("sentiment_and_redflags", "diff_facts")

    graph.add_conditional_edges(
        "diff_facts", nodes.has_discrepancies,
        {"explain_discrepancies": "explain_discrepancies", "score_confidence": "score_confidence"},
    )
    graph.add_edge("explain_discrepancies", "score_confidence")

    graph.add_conditional_edges(
        "score_confidence", nodes.route_review,
        {"flag_for_human_review": "flag_for_human_review", "auto_summarize": "auto_summarize"},
    )
    graph.add_edge("flag_for_human_review", END)
    graph.add_edge("auto_summarize", END)

    return graph.compile()


def build_yes_no_graph(nodes: ReferenceCheckNodes):
    graph = StateGraph(ReferenceCheckState)

    graph.add_node("evaluate_yes_no_form", nodes.evaluate_yes_no_form)
    graph.add_node("sentiment_from_comments", nodes.sentiment_from_comments)
    graph.add_node("score_confidence", nodes.score_confidence)
    graph.add_node("flag_for_human_review", nodes.flag_for_human_review)
    graph.add_node("auto_summarize", nodes.auto_summarize)

    graph.add_edge(START, "evaluate_yes_no_form")
    graph.add_conditional_edges(
        "evaluate_yes_no_form", nodes.has_comments,
        {"sentiment_from_comments": "sentiment_from_comments", "score_confidence": "score_confidence"},
    )
    graph.add_edge("sentiment_from_comments", "score_confidence")

    graph.add_conditional_edges(
        "score_confidence", nodes.route_review,
        {"flag_for_human_review": "flag_for_human_review", "auto_summarize": "auto_summarize"},
    )
    graph.add_edge("flag_for_human_review", END)
    graph.add_edge("auto_summarize", END)

    return graph.compile()


def build_reference_graphs(llm_provider: Optional[BaseLLMProvider] = None) -> tuple:
    """One ReferenceCheckNodes instance, both compiled graphs."""
    nodes = ReferenceCheckNodes(llm_provider)
    return build_open_ended_graph(nodes), build_yes_no_graph(nodes)


if __name__ == "__main__":
    from refcheck.llm.providers import get_provider
    open_graph, yes_no_graph = build_reference_graphs(get_provider())
    print("--- REF1 (open text) graph ---")
    print(open_graph.get_graph().draw_mermaid())
    print("\n--- REF2 (yes/no) graph ---")
    print(yes_no_graph.get_graph().draw_mermaid())
