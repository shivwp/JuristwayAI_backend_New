import os
import re
import logging
from redis import Redis

from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver

from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_core.messages import HumanMessage

from core.config import settings
from models.state import AgentState
from services.agent.tools import legal_tools

logger = logging.getLogger(__name__)
from dotenv import load_dotenv
load_dotenv()
# --- 1. INFRASTRUCTURE SETUP ---

# Memory Checkpointer (In-memory for development)
memory = MemorySaver()

# Redis Client
redis_client = Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=6379,
    decode_responses=True
)

# Embeddings (Used if you want to upgrade to true Semantic Caching later)
embeddings = GoogleGenerativeAIEmbeddings(
    model="models/gemini-embedding-001",
    google_api_key=settings.GEMINI_API_KEY,
    output_dimensionality=3072,
    task_type="retrieval_query"

)

# LLM with Tool Binding
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash-lite",
    google_api_key=settings.GEMINI_API_KEY,
    streaming=True
).bind_tools(legal_tools)

# --- 2. LANGGRAPH WORKFLOW ---

async def call_model(state: AgentState):
    response = await llm.ainvoke(state["messages"])
    return {"messages": [response]}

def should_continue(state: AgentState):
    last_message = state["messages"][-1]
    return "tools" if last_message.tool_calls else END

workflow = StateGraph(AgentState)
workflow.add_node("agent", call_model)
workflow.add_node("tools", ToolNode(legal_tools))

workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", should_continue)
workflow.add_edge("tools", "agent")

agent_executor = workflow.compile(checkpointer=memory)

# --- 3. ORCHESTRATION LOGIC ---

async def run_juristway_ai(query: str, thread_id: str):
    cache_key = f"cache:v1:{query.strip().lower()}"
    
    try:
        cached_res = redis_client.get(cache_key)
        if cached_res: return {"answer": cached_res, "source": "redis", "link": None}
    except Exception: pass

    config = {"configurable": {"thread_id": thread_id}}
    result = await agent_executor.ainvoke({"messages": [HumanMessage(content=query)]}, config)
    
    final_answer = result["messages"][-1].content
    # Extract Source Reference
    source_pdf = None
    for msg in reversed(result["messages"]):
        if msg.type == "tool":
            match = re.search(r"Source:\s*([\w-]+\.pdf)", msg.content)
            if match:
                source_pdf = match.group(1)
                break
            
    follow_up_link = None
    for msg in reversed(result["messages"]):
        if msg.type == "tool":
            # This regex will now catch the standardized 'Source: filename.pdf'
            match = re.search(r"Source:\s*([\w-]+\.pdf)", msg.content)
            if match:
                follow_up_link = f"https://your-legal-docs.com/view/{match.group(1)}"
                break

    # Cache the result
    try:
        redis_client.setex(cache_key, 3600, final_answer)
    except Exception: pass

    return {"answer": final_answer, "source": "llm", "link": follow_up_link}