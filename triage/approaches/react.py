"""A small ReAct loop built as a LangGraph StateGraph, with a hard step cap.

agent -> (tool calls?) -> tools -> agent ... ; when the cap is hit with a tool call still pending,
the pending calls are answered with a 'limit reached' message so the history stays valid, then the
model is asked for its final typed answer.
"""
from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from triage.approaches.common import UsageTracker, structured_call, with_retries
from triage.prompts import FINALIZE_PROMPT


class ReactState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    steps: int


def build_graph(llm, tools, max_steps: int, tracker: UsageTracker):
    bound = llm.bind_tools(tools)

    def agent(state: ReactState, config) -> dict:  # noqa: ANN001
        # retried like every model call: a malformed tool call from the server should not end the run
        resp = with_retries(lambda: bound.invoke(state["messages"], config), tracker, where="agent_step")
        return {"messages": [resp], "steps": state["steps"] + 1}

    def route(state: ReactState) -> str:
        last = state["messages"][-1]
        if not getattr(last, "tool_calls", None):
            return END
        return "tools" if state["steps"] < max_steps else "cap"

    def cap(state: ReactState) -> dict:
        last = state["messages"][-1]
        return {"messages": [ToolMessage(content="Step limit reached; this tool call was not run.", tool_call_id=tc["id"])
                             for tc in last.tool_calls]}

    g = StateGraph(ReactState)
    g.add_node("agent", agent)
    g.add_node("tools", ToolNode(tools))
    g.add_node("cap", cap)
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", route, {"tools": "tools", "cap": "cap", END: END})
    g.add_edge("tools", "agent")
    g.add_edge("cap", END)
    return g.compile()


def run_react(llm, system: str, user: str, tools, schema, tracker: UsageTracker, max_steps: int = 8,
              final_prompt: str = FINALIZE_PROMPT):
    """Investigate with tools, then return (typed answer, message history, model steps used)."""
    graph = build_graph(llm, tools, max_steps, tracker)
    out = graph.invoke({"messages": [SystemMessage(content=system), HumanMessage(content=user)], "steps": 0},
                       {"callbacks": [tracker], "recursion_limit": 2 * max_steps + 6})
    msgs = out["messages"]
    answer = structured_call(llm, schema, msgs + [HumanMessage(content=final_prompt)], tracker)
    return answer, msgs, out["steps"]
