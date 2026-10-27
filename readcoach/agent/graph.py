"""LangGraph 状态图：agent ⇄ tools 的循环。

选 LangGraph 而不是直接写 while 循环，有两个实际好处：
1. 循环边界由框架管，天然带递归上限，模型反复调工具不会把进程跑死；
2. 图结构本身就是汇报时那张架构图，图长什么样代码就长什么样，不用另外画。
"""

from functools import lru_cache
from typing import Annotated, TypedDict

from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from config import BASE_URL, DASHSCOPE_API_KEY, MODEL_NAME
from tools import ALL_TOOLS


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


def build_llm(model: str | None = None, temperature: float = 0.3) -> ChatOpenAI:
    """百炼的 OpenAI 兼容端点，换模型只改 environment 变量。"""
    return ChatOpenAI(
        model=model or MODEL_NAME,
        base_url=BASE_URL,
        api_key=DASHSCOPE_API_KEY or "EMPTY",
        temperature=temperature,
        timeout=90,
        max_retries=1,
    )


@lru_cache(maxsize=4)
def get_graph(model: str | None = None, temperature: float = 0.3):
    llm_with_tools = build_llm(model, temperature).bind_tools(ALL_TOOLS)

    def agent_node(state: AgentState) -> dict:
        return {"messages": [llm_with_tools.invoke(state["messages"])]}

    builder = StateGraph(AgentState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", ToolNode(ALL_TOOLS))

    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent",
        tools_condition,
        {"tools": "tools", END: END},
    )
    builder.add_edge("tools", "agent")

    return builder.compile()
