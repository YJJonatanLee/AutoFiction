from langgraph.graph import END, StateGraph

from .state import NarrativeState
from .nodes import (
    context_loader,
    novel_writer,
    output_parser,
    sequence_creator,
    sequence_generator,
    state_updater,
)


def should_continue(state: NarrativeState) -> str:
    if state.get("error"):
        return "end"
    if state["current_sequence_id"] <= state["max_sequences"]:
        return "continue"
    return "end"


def build_graph() -> StateGraph:
    graph = StateGraph(NarrativeState)

    graph.add_node("context_loader", context_loader)
    graph.add_node("sequence_generator", sequence_generator)
    graph.add_node("output_parser", output_parser)
    graph.add_node("state_updater", state_updater)
    graph.add_node("novel_writer", novel_writer)
    graph.add_node("sequence_creator", sequence_creator)

    graph.set_entry_point("context_loader")

    graph.add_edge("context_loader", "sequence_generator")
    graph.add_edge("sequence_generator", "output_parser")
    graph.add_edge("output_parser", "state_updater")
    graph.add_edge("state_updater", "novel_writer")
    graph.add_edge("novel_writer", "sequence_creator")

    graph.add_conditional_edges(
        "sequence_creator",
        should_continue,
        {
            "continue": "context_loader",
            "end": END,
        },
    )

    return graph.compile()
