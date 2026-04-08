"""
agents/orchestrator.py  —  Primary + Sub-Agent Coordination
Each sub-agent holds an MCPClient reference and calls tools through it.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from mcp_servers.mcp_connect import MCPClient, MCPServerType

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  BASE SUB-AGENT
# ──────────────────────────────────────────────

class SubAgent:
    """Base class for all sub-agents."""
    name: str = "base"

    def __init__(self, mcp: MCPClient):
        self.mcp = mcp

    async def run(self, intent: str, params: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError


# ──────────────────────────────────────────────
#  CALENDAR SUB-AGENT
# ──────────────────────────────────────────────

class CalendarAgent(SubAgent):
    name = "calendar"

    async def run(self, intent: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if intent == "create_event":
            return await self.mcp.invoke_tool("create_event", params)
        if intent == "list_events":
            return await self.mcp.invoke_tool("list_events", params)
        if intent == "find_free_slot":
            return await self.mcp.invoke_tool("find_free_slot", params)
        if intent == "delete_event":
            return await self.mcp.invoke_tool("delete_event", params)
        return {"error": f"CalendarAgent: unknown intent '{intent}'"}


# ──────────────────────────────────────────────
#  TASK MANAGER SUB-AGENT
# ──────────────────────────────────────────────

class TaskAgent(SubAgent):
    name = "task"

    async def run(self, intent: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if intent == "create_task":
            result = await self.mcp.invoke_tool("create_task", params)
            # Also persist to DB for history
            await self.mcp.invoke_tool("db_execute", {
                "sql": "INSERT INTO agent_data (key, value) VALUES (:k, :v)",
                "params": {"k": "task_created", "v": str(result)},
            })
            return result
        if intent == "list_tasks":
            return await self.mcp.invoke_tool("list_tasks", params)
        if intent == "update_task_status":
            return await self.mcp.invoke_tool("update_task_status", params)
        if intent == "get_task_summary":
            return await self.mcp.invoke_tool("get_task_summary", {})
        return {"error": f"TaskAgent: unknown intent '{intent}'"}


# ──────────────────────────────────────────────
#  NOTES SUB-AGENT
# ──────────────────────────────────────────────

class NotesAgent(SubAgent):
    name = "notes"

    async def run(self, intent: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if intent == "create_note":
            return await self.mcp.invoke_tool("create_note", params)
        if intent == "search_notes":
            return await self.mcp.invoke_tool("search_notes", params)
        if intent == "get_note":
            return await self.mcp.invoke_tool("get_note", params)
        if intent == "update_note":
            return await self.mcp.invoke_tool("update_note", params)
        return {"error": f"NotesAgent: unknown intent '{intent}'"}


# ──────────────────────────────────────────────
#  ORCHESTRATOR (PRIMARY AGENT)
# ──────────────────────────────────────────────

class OrchestratorAgent:
    """
    Primary agent — receives a user message, classifies intent,
    delegates to the right sub-agent, aggregates and returns result.
    """

    def __init__(self, mcp: MCPClient):
        self.mcp = mcp
        self._agents: Dict[str, SubAgent] = {}
        self._history: List[Dict] = []

        # Register sub-agents
        for agent_cls in (CalendarAgent, TaskAgent, NotesAgent):
            a = agent_cls(mcp)
            self._agents[a.name] = a

    # ── Main entry point ──────────────────────

    async def handle(self, user_message: str) -> Dict[str, Any]:
        ts = datetime.utcnow().isoformat()
        self._history.append({"role": "user", "content": user_message, "ts": ts})

        routing = self._classify(user_message)
        logger.info("Routing: agent=%s  intent=%s", routing["agent"], routing["intent"])

        agent = self._agents.get(routing["agent"])
        if not agent:
            reply = {"message": "I'm not sure how to help with that. "
                                "Try: schedule, task, or note commands."}
        else:
            raw    = await agent.run(routing["intent"], routing["params"])
            reply  = self._format_reply(routing, raw)

        self._history.append({"role": "assistant", "content": reply["message"], "ts": ts})
        return reply

    # ── Intent classification ─────────────────

    def _classify(self, text: str) -> Dict[str, Any]:
        t = text.lower()

        # Calendar patterns
        if any(kw in t for kw in ("schedule", "meeting", "calendar", "appointment", "event")):
            if any(kw in t for kw in ("create", "add", "book", "set up")):
                return {"agent": "calendar", "intent": "create_event",
                        "params": self._extract_event_params(text)}
            if any(kw in t for kw in ("free", "available", "slot")):
                return {"agent": "calendar", "intent": "find_free_slot",
                        "params": {"duration_minutes": 60}}
            return {"agent": "calendar", "intent": "list_events",
                    "params": {"start_date": datetime.utcnow().strftime("%Y-%m-%d"),
                               "end_date":   "2099-12-31"}}

        # Task patterns
        if any(kw in t for kw in ("task", "todo", "assign", "deadline", "backlog")):
            if any(kw in t for kw in ("create", "add", "new")):
                return {"agent": "task", "intent": "create_task",
                        "params": {"title": text[:80], "priority": "medium"}}
            if any(kw in t for kw in ("done", "complete", "finish")):
                return {"agent": "task", "intent": "update_task_status",
                        "params": {"task_id": "task_1", "status": "completed"}}
            if any(kw in t for kw in ("summary", "report", "stats")):
                return {"agent": "task", "intent": "get_task_summary", "params": {}}
            return {"agent": "task", "intent": "list_tasks",
                    "params": {"status": "all"}}

        # Notes patterns
        if any(kw in t for kw in ("note", "save", "remember", "jot", "write down")):
            if any(kw in t for kw in ("search", "find", "look up")):
                return {"agent": "notes", "intent": "search_notes",
                        "params": {"query": text}}
            return {"agent": "notes", "intent": "create_note",
                    "params": {"title": "Quick Note", "content": text}}

        return {"agent": "", "intent": "", "params": {}}

    def _extract_event_params(self, text: str) -> Dict[str, Any]:
        """Minimal extraction — replace with LLM call in production."""
        return {
            "title":       text[:60],
            "start_time":  f"{datetime.utcnow().strftime('%Y-%m-%d')}T10:00:00",
            "end_time":    f"{datetime.utcnow().strftime('%Y-%m-%d')}T11:00:00",
            "description": text,
        }

    def _format_reply(self, routing: Dict, raw: Dict) -> Dict[str, Any]:
        if "error" in raw:
            return {"message": f"Error: {raw['error']}", "data": raw}
        return {
            "message": (f"Done — {routing['agent']} agent handled '{routing['intent']}'. "
                        f"Result: {json_summary(raw)}"),
            "agent":   routing["agent"],
            "intent":  routing["intent"],
            "data":    raw,
        }


# ──────────────────────────────────────────────
#  Helper
# ──────────────────────────────────────────────

def json_summary(data: Dict) -> str:
    import json
    s = json.dumps(data, default=str)
    return s[:200] + "…" if len(s) > 200 else s
