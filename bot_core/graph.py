import os
import json
from typing import Annotated, Sequence, TypedDict, Dict, Any, List, Optional
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from bot_core.config import GEMINI_API_KEY, GEMINI_MODEL, DOCS_DIR
from bot_core.knowledge import get_co_founder_system_prompt
from bot_core.pipeline import (
    scan_youtube_trends, extract_moments, render_vertical_clip,
    verify_clip, log_payout, find_top_video, generate_viral_hook,
    find_live_streams, translate_clip_subtitles
)

def extract_text(content: Any) -> str:
    """Extract plain text from string or structured LangChain list."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        res = []
        for c in content:
            if isinstance(c, dict) and c.get("type") == "text":
                res.append(c.get("text", ""))
            elif isinstance(c, str):
                res.append(c)
        return "".join(res)
    return str(content)

# --- TOOLS ---

@tool
def get_campaigns_info() -> str:
    """Membaca daftar kampanye Paid Clipping (Whop / Clip.tech), tarif per 1K views, dan aturan validasi saat ini."""
    camp_file = DOCS_DIR / "campaigns.md"
    if camp_file.exists():
        return camp_file.read_text(encoding="utf-8")
    return "File campaigns.md belum ditemukan."

@tool
def scan_youtube_top_trends(query: str = "gta 6", hours: int = 48) -> str:
    """Memindai video GTA 6 trending di YouTube yang memiliki views per jam tertinggi (Skill: trend-radar)."""
    results = scan_youtube_trends(query=query, hours=hours, limit=5)
    if not results:
        return "Tidak ditemukan video trending untuk query tersebut."
    formatted = ["Daftar Video Trending Saat Ini:"]
    for r in results:
        formatted.append(f"- #{r['rank']} {r['channel']}: {r['title_link']} ({r['views_per_hour']} views/jam)")
    return "\n".join(formatted)

@tool
def find_active_live_streams(query: str = "gta 6", limit: int = 5) -> str:
    """Mencari live stream GTA 6 yang sedang tayang di YouTube dan Twitch dengan concurrent viewer tertinggi (Skill: stream-finder)."""
    streams = find_live_streams(query=query, limit=limit)
    if not streams:
        return "Tidak ada live stream aktif ditemukan untuk topik tersebut."
    res = ["Live Stream Aktif Saat Ini:"]
    for s in streams:
        plat = s.get("platform", "stream").upper()
        res.append(f"- [{plat}] {s.get('channel', 'Streamer')} ({s.get('viewers', 0):,} viewers): {s.get('title', '')} -> {s.get('url', '')}")
    return "\n".join(res)

@tool
def generate_viral_hooks_tool(streamer_or_topic: str, context: str = "") -> str:
    """Menulis 3 variasi hook viral dan judul on-screen reaction sesuai formula hook-writer (Skill: hook-writer)."""
    hook, title = generate_viral_hook(streamer_or_topic, context, streamer_or_topic)
    return f"Rekomendasi Hook & Judul:\n1. Title Seam: {title}\n2. Hook Opener: {hook}\nFormula: Sentence-case/CAPS 2-3 key words, curiosity gap tinggi."

@tool
def process_clipping_video(video_url: str, layout: str = "react", custom_hook_or_title: str = "") -> str:
    """
    Mengunduh video atau mencari video YouTube berdasarkan query/nama streamer,
    menganalisis transkrip dengan Whisper, memilih momen viral terbaik, 
    dan merender klip vertikal 9:16 (Skill: twitch-reaction layout 'react' untuk split-screen: muka streamer di atas, game di bawah; atau 'blur' jika pure gameplay).
    """
    try:
        job_dir, candidates, err = extract_moments(video_url, top=6, max_minutes=12)
        if not candidates or not job_dir:
            return f"Gagal mendeteksi momen atau video tidak ditemukan: {err}"
            
        pick = 1
        best_cand = candidates[0]
        cand_text = best_cand.get("text", "")
        
        if custom_hook_or_title:
            hook = custom_hook_or_title
            title = custom_hook_or_title
        else:
            hook, title = generate_viral_hook(video_url, cand_text, "", candidate=best_cand)
        
        clip_path = render_vertical_clip(
            job_dir=job_dir,
            pick=pick,
            layout=layout,
            hook=hook,
            title=title,
            title_style="box",
            captions="word"
        )
        if clip_path and clip_path.exists():
            return json.dumps({
                "status": "success",
                "clip_path": str(clip_path),
                "duration": best_cand.get("end", 0) - best_cand.get("start", 0),
                "summary": cand_text[:100],
                "title": title,
                "hook": hook,
                "layout": layout,
                "job_id": job_dir.name
            })
        return "Render video gagal dijalankan."
    except Exception as e:
        return f"Terjadi error saat memproses klip: {str(e)}"

TOOLS = [
    get_campaigns_info, scan_youtube_top_trends, find_active_live_streams,
    generate_viral_hooks_tool, process_clipping_video
]

# --- LANGGRAPH STATE ---

class AgentState(TypedDict):
    messages: Sequence[BaseMessage]
    current_clip: Optional[Dict[str, Any]]

# Initialize LLM with Gemini
llm = ChatGoogleGenerativeAI(
    model=GEMINI_MODEL,
    google_api_key=GEMINI_API_KEY
).bind_tools(TOOLS)

def agent_node(state: AgentState):
    messages = list(state["messages"])
    system_prompt = get_co_founder_system_prompt()
    
    # Inject system message if not present
    if not messages or not isinstance(messages[0], SystemMessage):
        messages.insert(0, SystemMessage(content=system_prompt))
    else:
        messages[0] = SystemMessage(content=system_prompt)
        
    response = llm.invoke(messages)
    return {"messages": [response]}

def should_continue(state: AgentState):
    messages = state["messages"]
    last_message = messages[-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return END

# Build Graph
workflow = StateGraph(AgentState)
workflow.add_node("agent", agent_node)
workflow.add_node("tools", ToolNode(TOOLS))

workflow.set_entry_point("agent")
workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
workflow.add_edge("tools", "agent")

co_founder_graph = workflow.compile()

def ask_co_founder(user_message: str, history: List[BaseMessage] = None) -> tuple[str, Optional[str]]:
    """
    Main entry point to communicate with the Co-founder Agent.
    Returns (assistant_text, clip_path_if_any).
    """
    msg_clean = (user_message or "").strip()
    if not msg_clean:
        msg_clean = "Halo Alex, apa update status kita?"

    # Sanitize message history
    messages: List[BaseMessage] = []
    if history:
        for m in history:
            txt = extract_text(getattr(m, "content", ""))
            if txt and txt.strip():
                if isinstance(m, HumanMessage):
                    messages.append(HumanMessage(content=txt.strip()))
                elif isinstance(m, AIMessage):
                    messages.append(AIMessage(content=txt.strip()))
                elif isinstance(m, SystemMessage):
                    messages.append(SystemMessage(content=txt.strip()))

    messages.append(HumanMessage(content=msg_clean))
    
    try:
        result = co_founder_graph.invoke({"messages": messages, "current_clip": None})
        final_raw = result["messages"][-1].content
        final_message = extract_text(final_raw)
        
        # Check if any tool result returned a clip_path
        clip_path = None
        for msg in reversed(result["messages"]):
            if hasattr(msg, "content"):
                txt = extract_text(msg.content)
                if "clip_path" in txt and ".mp4" in txt:
                    try:
                        data = json.loads(txt)
                        clip_path = data.get("clip_path")
                        if clip_path:
                            break
                    except Exception:
                        pass
                        
        return final_message, clip_path
    except Exception as e:
        print(f"[ask_co_founder error]: {e}")
        return f"Bro, sistem AI sempat hiccup ({e}), tapi jangan khawatir pipeline kita tetap siap jalan!", None
