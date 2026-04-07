"""
Primary Orchestrator — Google ADK multi-agent system for SSC Exam Scheduler
--------------------------------------------------------------------
Architecture:
  root_agent  (entry point: saves prompt → routes to workflow)
    └── SequentialAgent: ssc_workflow
          ├── coordinator_agent  ← calls task/schedule/notes/youtube tools
          └── formatter_agent    ← turns results into student-friendly response

All sub-agent logic lives in the four *_tool functions below, which are
plain Python callables — ADK auto-generates the Gemini function schema
from the type hints and docstrings.
"""

import asyncio
import concurrent.futures
import json
import logging
import os
import uuid
from datetime import datetime

from google.adk import Agent
from google.adk.agents import SequentialAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.tool_context import ToolContext
from google.genai.types import Content, Part

from agents.task_agent import TaskAgent
from agents.schedule_agent import ScheduleAgent
from agents.notes_agent import NotesAgent
from agents.youtube_agent import YouTubeAgent
from db.database import Database

logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────
MODEL    = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
APP_NAME = "ssc_exam_scheduler"
_db      = Database()   # shared, thread-safe (SQLite WAL mode)

# ── Sub-agent tool functions ───────────────────────────────────────────────────

def task_tool(action: str, data: str = "{}") -> str:
    """
    Manage study tasks for SSC exam preparation.

    Args:
        action: create_task | list_tasks | update_task | complete_task | get_stats
        data:   JSON string. Examples:
                  create_task  -> {"title":"...", "subject":"Quantitative Aptitude",
                                   "priority":"high|medium|low", "due_date":"YYYY-MM-DD"}
                  list_tasks   -> {"subject":"...", "status":"pending|completed"}
                  complete_task-> {"task_id":"..."}
                  get_stats    -> {}
    Returns:
        JSON string with the TaskAgent result.
    """
    try:
        payload = json.loads(data) if isinstance(data, str) else data
    except json.JSONDecodeError:
        payload = {}
    return json.dumps(TaskAgent(_db).handle(action, payload))


def schedule_tool(action: str, data: str = "{}") -> str:
    """
    Manage SSC exam dates and daily study timetables.

    Args:
        action: set_exam_date | get_schedule | create_daily_plan | get_subject_plan | get_upcoming
        data:   JSON string. Examples:
                  set_exam_date    -> {"exam_name":"SSC CGL Tier-1","exam_date":"YYYY-MM-DD"}
                  create_daily_plan-> {"study_mode":"light|moderate|intensive","days":7}
                  get_subject_plan -> {"subject":"Reasoning Ability"}
    Returns:
        JSON string with the ScheduleAgent result.
    """
    try:
        payload = json.loads(data) if isinstance(data, str) else data
    except json.JSONDecodeError:
        payload = {}
    return json.dumps(ScheduleAgent(_db).handle(action, payload))


def notes_tool(action: str, data: str = "{}") -> str:
    """
    Create and retrieve study notes, formulas, and key concepts.

    Args:
        action: create_note | get_notes | search_notes | get_by_subject
        data:   JSON string. Examples:
                  create_note   -> {"title":"SI Formula","content":"SI=PRT/100",
                                    "subject":"Quantitative Aptitude","is_important":true}
                  search_notes  -> {"query":"percentage"}
                  get_by_subject-> {"subject":"English Language"}
    Returns:
        JSON string with the NotesAgent result.
    """
    try:
        payload = json.loads(data) if isinstance(data, str) else data
    except json.JSONDecodeError:
        payload = {}
    return json.dumps(NotesAgent(_db).handle(action, payload))


def youtube_tool(action: str, data: str = "{}") -> str:
    """
    Save and find YouTube educational video links for SSC subjects.

    Args:
        action: save_link | get_links | search_links | get_by_subject
        data:   JSON string. Examples:
                  save_link     -> {"title":"SSC Maths Tricks","url":"https://youtube.com/...",
                                    "subject":"Quantitative Aptitude","channel":"Adda247"}
                  get_by_subject-> {"subject":"Reasoning Ability"}
                  search_links  -> {"query":"percentage tricks"}
    Returns:
        JSON string with the YouTubeAgent result.
    """
    try:
        payload = json.loads(data) if isinstance(data, str) else data
    except json.JSONDecodeError:
        payload = {}
    return json.dumps(YouTubeAgent(_db).handle(action, payload))


def save_user_prompt(tool_context: ToolContext, prompt: str) -> dict:
    """
    Save the student's message into ADK session state so downstream
    agents can access it via the {PROMPT} template variable.

    Args:
        prompt: The student's exact message text.
    Returns:
        Status dict confirming the save.
    """
    tool_context.state["PROMPT"]    = prompt
    tool_context.state["TIMESTAMP"] = datetime.now().isoformat()
    logger.info(f"[ADK State] PROMPT saved ({len(prompt)} chars)")
    return {"status": "saved"}


# ── Agent definitions ──────────────────────────────────────────────────────────

# Step 1 of workflow — Coordinator decides which tools to call
coordinator_agent = Agent(
    name="ssc_coordinator",
    model=MODEL,
    description="Analyses the student's SSC request and calls the right tools.",
    instruction="""You are the SSC Exam Scheduler Coordinator for Indian government exam students.

Your job is to understand the student request in {PROMPT} and call the correct tool(s):
  • task_tool     — create / list / complete study tasks, get progress stats
  • schedule_tool — set exam dates, build daily timetables, get subject topic plans
  • notes_tool    — create, search, and retrieve study notes and formulas
  • youtube_tool  — save and find YouTube study videos by subject

Rules:
1. Always pass `data` as a valid JSON string (double-quoted keys/values).
2. Multi-step requests (e.g. "set exam date AND create a plan") → call multiple tools.
3. Date format: YYYY-MM-DD.
4. Valid subjects: Quantitative Aptitude | English Language | General Awareness |
   Reasoning Ability | Computer Knowledge.

Student request: {PROMPT}
""",
    tools=[task_tool, schedule_tool, notes_tool, youtube_tool],
    output_key="coordinator_result",
)

# Step 2 of workflow — Formatter shapes the response for students
formatter_agent = Agent(
    name="ssc_formatter",
    model=MODEL,
    description="Formats coordinator results into clear, encouraging student responses.",
    instruction="""You are the friendly SSC Scholar assistant.

Turn COORDINATOR_RESULT into a helpful response for an SSC exam student
(CGL / CHSL / MTS / CPO).

Guidelines:
• Use emojis sparingly (✅ 📅 📝 ▶️ 📊) for readability.
• Present schedules, tasks, and notes clearly with line breaks.
• Be encouraging ("Great choice!", "You're on track!").
• For schedules: show key highlights, not raw JSON.
• For notes saved: confirm what was saved and remind to revise.
• Keep under ~300 words unless a detailed plan was requested.
• End with one specific actionable next step.

COORDINATOR_RESULT:
{coordinator_result}
""",
)

# Sequential workflow: coordinator → formatter
ssc_workflow = SequentialAgent(
    name="ssc_workflow",
    description="Full SSC prep workflow: call domain tools then format the response.",
    sub_agents=[coordinator_agent, formatter_agent],
)

# Root agent: saves prompt to state, then transfers to workflow
root_agent = Agent(
    name="ssc_root",
    model=MODEL,
    description="Entry point: saves student prompt then routes to ssc_workflow.",
    instruction="""You are the SSC Scholar entry point.

When the student sends a message:
1. Call `save_user_prompt` with their EXACT message as `prompt`.
2. After the tool returns, immediately transfer control to `ssc_workflow`.

Do NOT answer the question yourself. Just save and transfer.
""",
    tools=[save_user_prompt],
    sub_agents=[ssc_workflow],
)

# ── ADK Runner (module-level singleton) ────────────────────────────────────────
_session_service = InMemorySessionService()
_runner = Runner(
    agent=root_agent,
    app_name=APP_NAME,
    session_service=_session_service,
)


# ── Async core ─────────────────────────────────────────────────────────────────
async def _run_async(user_message: str, session_id: str) -> str:
    """Execute the ADK agent graph and return the final text response."""
    # Create session if it does not exist yet
    existing = await _session_service.get_session(
        app_name=APP_NAME, user_id="student", session_id=session_id
    )
    if existing is None:
        await _session_service.create_session(
            app_name=APP_NAME, user_id="student", session_id=session_id
        )

    new_message = Content(role="user", parts=[Part(text=user_message)])

    final_text = ""
    async for event in _runner.run_async(
        user_id="student",
        session_id=session_id,
        new_message=new_message,
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_text = "".join(
                p.text for p in event.content.parts
                if hasattr(p, "text") and p.text
            )
    return final_text or "Your request was processed successfully."


# ── Public sync interface called by FastAPI ────────────────────────────────────
def orchestrate(user_message: str, conversation_history: list = None) -> dict:
    """
    Synchronous wrapper around the ADK async graph.
    Safe for both standalone uvicorn and Cloud Run.
    """
    # Stable session_id derived from history so follow-up messages share a session
    session_id = (
        f"s_{abs(hash(str(conversation_history))) % 100000:05d}"
        if conversation_history
        else f"s_{uuid.uuid4().hex[:8]}"
    )

    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Running inside uvicorn's event loop — use a dedicated thread
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                response_text = pool.submit(
                    asyncio.run, _run_async(user_message, session_id)
                ).result(timeout=120)
        else:
            response_text = asyncio.run(_run_async(user_message, session_id))

    except Exception as exc:
        logger.error(f"ADK orchestration error: {exc}", exc_info=True)
        response_text = f"⚠️ I encountered an issue: {exc}"

    updated_history = list(conversation_history or [])
    updated_history.append({"role": "user",      "content": user_message})
    updated_history.append({"role": "assistant",  "content": response_text})

    return {"response": response_text, "conversation_history": updated_history}
