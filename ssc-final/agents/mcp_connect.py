"""
mcp_connect.py  —  MCP Server Connection Layer
Connects the multi-agent system to Calendar, Task Manager, Notes,
and AlloyDB MCP servers using the Model Context Protocol.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

import aiohttp

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# 1.  Server registry & config
# ─────────────────────────────────────────────

class MCPServerType(Enum):
    CALENDAR     = "calendar"
    TASK_MANAGER = "task_manager"
    NOTES        = "notes"
    DATABASE     = "database"


@dataclass
class MCPServerConfig:
    server_type : MCPServerType
    host        : str
    port        : int
    api_key     : Optional[str] = None
    timeout     : int = 30


# Default config — override with env vars in production
DEFAULT_SERVERS: List[MCPServerConfig] = [
    MCPServerConfig(MCPServerType.CALENDAR,     "localhost", 8001),
    MCPServerConfig(MCPServerType.TASK_MANAGER, "localhost", 8002),
    MCPServerConfig(MCPServerType.NOTES,        "localhost", 8003),
    MCPServerConfig(MCPServerType.DATABASE,     "localhost", 8004),
]


# ─────────────────────────────────────────────
# 2.  Tool descriptor
# ─────────────────────────────────────────────

@dataclass
class MCPTool:
    name        : str
    description : str
    parameters  : Dict[str, Any]
    server_type : MCPServerType


# ─────────────────────────────────────────────
# 3.  MCPClient  (connects + dispatches tools)
# ─────────────────────────────────────────────

class MCPClient:
    """
    Manages connections to multiple MCP tool servers.
    Agents call  invoke_tool(tool_name, params)  — routing is automatic.
    """

    def __init__(self, servers: Optional[List[MCPServerConfig]] = None):
        self.servers: Dict[MCPServerType, MCPServerConfig] = {
            s.server_type: s for s in (servers or DEFAULT_SERVERS)
        }
        self.tools: Dict[str, MCPTool] = {}   # name → MCPTool

    # ── Connection ─────────────────────────────

    async def connect_all(self) -> None:
        """Connect to all registered servers, discover their tools."""
        results = await asyncio.gather(
            *[self._handshake(st) for st in self.servers],
            return_exceptions=True,
        )
        for server_type, result in zip(self.servers, results):
            if isinstance(result, Exception):
                logger.error("MCP connect failed [%s]: %s", server_type.value, result)
            else:
                logger.info("MCP connected  [%s] — %d tools registered",
                            server_type.value, result)

    async def _handshake(self, server_type: MCPServerType) -> int:
        """Fetch the tool manifest from one MCP server."""
        cfg = self.servers[server_type]
        headers = self._auth_headers(cfg)
        url = f"http://{cfg.host}:{cfg.port}/mcp/v1/tools"

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers,
                                   timeout=aiohttp.ClientTimeout(total=cfg.timeout)) as resp:
                resp.raise_for_status()
                data = await resp.json()

        count = 0
        for t in data.get("tools", []):
            tool = MCPTool(
                name        = t["name"],
                description = t["description"],
                parameters  = t.get("parameters", {}),
                server_type = server_type,
            )
            self.tools[t["name"]] = tool
            count += 1
        return count

    # ── Tool invocation ─────────────────────────

    async def invoke_tool(self, tool_name: str,
                          parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool on its registered MCP server."""
        if tool_name not in self.tools:
            raise ValueError(
                f"Unknown tool '{tool_name}'. "
                f"Available: {sorted(self.tools)}"
            )

        tool = self.tools[tool_name]
        cfg  = self.servers[tool.server_type]
        url  = f"http://{cfg.host}:{cfg.port}/mcp/v1/invoke"

        payload = {
            "tool"             : tool_name,
            "parameters"       : parameters,
            "protocol_version" : "1.0",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload,
                headers={**self._auth_headers(cfg), "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=cfg.timeout),
            ) as resp:
                body = await resp.json()
                if resp.status != 200:
                    raise RuntimeError(
                        f"Tool '{tool_name}' failed: {body.get('error', resp.status)}"
                    )
                return body.get("result", {})

    # ── Helpers ─────────────────────────────────

    @staticmethod
    def _auth_headers(cfg: MCPServerConfig) -> Dict[str, str]:
        return {"Authorization": f"Bearer {cfg.api_key}"} if cfg.api_key else {}

    def tools_for(self, *server_types: MCPServerType) -> List[MCPTool]:
        return [t for t in self.tools.values() if t.server_type in server_types]

    def list_tools(self) -> List[str]:
        return sorted(self.tools)


# ─────────────────────────────────────────────
# 4.  Calendar MCP Server  (FastAPI mini-service)
# ─────────────────────────────────────────────

def build_calendar_server():
    from fastapi import FastAPI
    from datetime import datetime, timedelta

    app = FastAPI(title="Calendar MCP Server")
    _db: List[Dict] = []

    MANIFEST = {"tools": [
        {"name": "create_event",
         "description": "Create a calendar event",
         "parameters": {
             "title":       {"type": "string",  "required": True},
             "start_time":  {"type": "string",  "required": True, "format": "ISO8601"},
             "end_time":    {"type": "string",  "required": True, "format": "ISO8601"},
             "description": {"type": "string",  "required": False},
             "attendees":   {"type": "array",   "required": False},
         }},
        {"name": "list_events",
         "description": "List events for a date range",
         "parameters": {
             "start_date": {"type": "string", "required": True},
             "end_date":   {"type": "string", "required": True},
         }},
        {"name": "find_free_slot",
         "description": "Find an available time slot",
         "parameters": {
             "duration_minutes": {"type": "integer", "required": True},
             "preferred_date":   {"type": "string",  "required": False},
         }},
        {"name": "delete_event",
         "description": "Delete a calendar event by ID",
         "parameters": {"event_id": {"type": "string", "required": True}}},
    ]}

    @app.get("/mcp/v1/tools")
    async def get_tools():
        return MANIFEST

    @app.post("/mcp/v1/invoke")
    async def invoke(payload: dict):
        tool   = payload["tool"]
        params = payload["parameters"]

        if tool == "create_event":
            ev = {"id": f"evt_{len(_db)+1}", **params}
            ev.setdefault("description", "")
            ev.setdefault("attendees", [])
            _db.append(ev)
            return {"result": {"status": "created", "event": ev}}

        if tool == "list_events":
            filtered = [e for e in _db
                        if params["start_date"] <= e["start_time"] <= params["end_date"]]
            return {"result": {"events": filtered, "count": len(filtered)}}

        if tool == "find_free_slot":
            date  = params.get("preferred_date", datetime.utcnow().strftime("%Y-%m-%d"))
            dur   = params["duration_minutes"]
            slot  = {"date": date,
                     "start_time": f"{date}T09:00:00",
                     "end_time":   f"{date}T{9+dur//60:02d}:{dur%60:02d}:00"}
            return {"result": {"free_slot": slot}}

        if tool == "delete_event":
            before = len(_db)
            _db[:] = [e for e in _db if e["id"] != params["event_id"]]
            return {"result": {"deleted": len(_db) < before}}

        return {"error": f"Unknown tool: {tool}"}, 400

    return app


# ─────────────────────────────────────────────
# 5.  Task Manager MCP Server
# ─────────────────────────────────────────────

def build_task_server():
    from fastapi import FastAPI

    app = FastAPI(title="Task Manager MCP Server")
    _db: List[Dict] = []

    MANIFEST = {"tools": [
        {"name": "create_task",
         "description": "Create a new task",
         "parameters": {
             "title":       {"type": "string",  "required": True},
             "description": {"type": "string",  "required": False},
             "due_date":    {"type": "string",  "required": False},
             "priority":    {"type": "string",  "enum": ["low","medium","high"]},
             "assignee":    {"type": "string",  "required": False},
         }},
        {"name": "list_tasks",
         "description": "List tasks with optional filters",
         "parameters": {
             "status":   {"type": "string", "enum": ["pending","in_progress","completed","all"]},
             "assignee": {"type": "string", "required": False},
             "priority": {"type": "string", "required": False},
         }},
        {"name": "update_task_status",
         "description": "Change status of a task",
         "parameters": {
             "task_id": {"type": "string", "required": True},
             "status":  {"type": "string", "enum": ["pending","in_progress","completed"]},
         }},
        {"name": "get_task_summary",
         "description": "Aggregate stats for all tasks",
         "parameters": {}},
    ]}

    @app.get("/mcp/v1/tools")
    async def get_tools():
        return MANIFEST

    @app.post("/mcp/v1/invoke")
    async def invoke(payload: dict):
        tool   = payload["tool"]
        params = payload["parameters"]

        if tool == "create_task":
            t = {"id": f"task_{len(_db)+1}",
                 "title":       params["title"],
                 "description": params.get("description", ""),
                 "due_date":    params.get("due_date", ""),
                 "priority":    params.get("priority", "medium"),
                 "assignee":    params.get("assignee", "unassigned"),
                 "status":      "pending"}
            _db.append(t)
            return {"result": {"status": "created", "task": t}}

        if tool == "list_tasks":
            rows = _db[:]
            if params.get("status") not in (None, "all"):
                rows = [r for r in rows if r["status"] == params["status"]]
            if params.get("assignee"):
                rows = [r for r in rows if r["assignee"] == params["assignee"]]
            if params.get("priority"):
                rows = [r for r in rows if r["priority"] == params["priority"]]
            return {"result": {"tasks": rows, "count": len(rows)}}

        if tool == "update_task_status":
            for t in _db:
                if t["id"] == params["task_id"]:
                    t["status"] = params["status"]
                    return {"result": {"updated": True, "task": t}}
            return {"error": "Task not found"}, 404

        if tool == "get_task_summary":
            return {"result": {
                "total":       len(_db),
                "pending":     sum(1 for t in _db if t["status"] == "pending"),
                "in_progress": sum(1 for t in _db if t["status"] == "in_progress"),
                "completed":   sum(1 for t in _db if t["status"] == "completed"),
                "high_priority": sum(1 for t in _db if t["priority"] == "high"),
            }}

        return {"error": f"Unknown tool: {tool}"}, 400

    return app


# ─────────────────────────────────────────────
# 6.  Notes MCP Server
# ─────────────────────────────────────────────

def build_notes_server():
    from fastapi import FastAPI
    from datetime import datetime

    app = FastAPI(title="Notes MCP Server")
    _db: List[Dict] = []

    MANIFEST = {"tools": [
        {"name": "create_note",
         "description": "Create a note",
         "parameters": {
             "title":   {"type": "string", "required": True},
             "content": {"type": "string", "required": True},
             "tags":    {"type": "array",  "required": False},
         }},
        {"name": "search_notes",
         "description": "Search notes by keyword or tag",
         "parameters": {
             "query": {"type": "string", "required": False},
             "tags":  {"type": "array",  "required": False},
         }},
        {"name": "get_note",
         "description": "Retrieve a note by ID",
         "parameters": {"note_id": {"type": "string", "required": True}}},
        {"name": "update_note",
         "description": "Update note content",
         "parameters": {
             "note_id": {"type": "string", "required": True},
             "content": {"type": "string", "required": True},
         }},
    ]}

    @app.get("/mcp/v1/tools")
    async def get_tools():
        return MANIFEST

    @app.post("/mcp/v1/invoke")
    async def invoke(payload: dict):
        tool   = payload["tool"]
        params = payload["parameters"]

        if tool == "create_note":
            n = {"id":         f"note_{len(_db)+1}",
                 "title":      params["title"],
                 "content":    params["content"],
                 "tags":       params.get("tags", []),
                 "created_at": datetime.utcnow().isoformat()}
            _db.append(n)
            return {"result": {"status": "created", "note": n}}

        if tool == "search_notes":
            rows = _db[:]
            if params.get("query"):
                q = params["query"].lower()
                rows = [n for n in rows if q in n["title"].lower() or q in n["content"].lower()]
            if params.get("tags"):
                rows = [n for n in rows if any(tag in n["tags"] for tag in params["tags"])]
            return {"result": {"notes": rows, "count": len(rows)}}

        if tool == "get_note":
            for n in _db:
                if n["id"] == params["note_id"]:
                    return {"result": {"note": n}}
            return {"error": "Note not found"}, 404

        if tool == "update_note":
            for n in _db:
                if n["id"] == params["note_id"]:
                    n["content"] = params["content"]
                    return {"result": {"updated": True, "note": n}}
            return {"error": "Note not found"}, 404

        return {"error": f"Unknown tool: {tool}"}, 400

    return app


# ─────────────────────────────────────────────
# 7.  Database MCP Server  (AlloyDB / Postgres)
# ─────────────────────────────────────────────

def build_database_server(db_url: Optional[str] = None):
    """
    Wraps AlloyDB (or any Postgres-compatible DB) as an MCP server.
    Set DB_URL env var: postgresql+asyncpg://user:pass@host/dbname
    """
    import os
    from fastapi import FastAPI

    app   = FastAPI(title="Database MCP Server")
    _url  = db_url or os.getenv("DB_URL", "sqlite+aiosqlite:///./local.db")

    MANIFEST = {"tools": [
        {"name": "db_query",
         "description": "Run a read-only SQL SELECT query",
         "parameters": {
             "sql":    {"type": "string", "required": True},
             "params": {"type": "array",  "required": False},
         }},
        {"name": "db_execute",
         "description": "Run an INSERT / UPDATE / DELETE statement",
         "parameters": {
             "sql":    {"type": "string", "required": True},
             "params": {"type": "array",  "required": False},
         }},
        {"name": "db_list_tables",
         "description": "List all tables in the database",
         "parameters": {}},
    ]}

    @app.on_event("startup")
    async def startup():
        import sqlalchemy.ext.asyncio as sa_async
        import sqlalchemy as sa
        engine = sa_async.create_async_engine(_url, echo=False)
        app.state.engine = engine
        # Create schema if needed
        async with engine.begin() as conn:
            await conn.execute(sa.text(
                "CREATE TABLE IF NOT EXISTS agent_data "
                "(id SERIAL PRIMARY KEY, key TEXT, value JSONB, created_at TIMESTAMPTZ DEFAULT now())"
            ))

    @app.get("/mcp/v1/tools")
    async def get_tools():
        return MANIFEST

    @app.post("/mcp/v1/invoke")
    async def invoke(payload: dict):
        import sqlalchemy as sa
        tool   = payload["tool"]
        params = payload["parameters"]

        async with app.state.engine.connect() as conn:
            if tool == "db_query":
                result = await conn.execute(
                    sa.text(params["sql"]), params.get("params") or {}
                )
                rows = [dict(r) for r in result.mappings()]
                return {"result": {"rows": rows, "count": len(rows)}}

            if tool == "db_execute":
                result = await conn.execute(
                    sa.text(params["sql"]), params.get("params") or {}
                )
                await conn.commit()
                return {"result": {"rows_affected": result.rowcount}}

            if tool == "db_list_tables":
                result = await conn.execute(sa.text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='public'"
                ))
                tables = [r[0] for r in result]
                return {"result": {"tables": tables}}

        return {"error": f"Unknown tool: {tool}"}, 400

    return app


# ─────────────────────────────────────────────
# 8.  Launch helper  (runs all servers locally)
# ─────────────────────────────────────────────

async def launch_all_servers():
    """Start all four MCP servers concurrently (for local dev)."""
    import uvicorn

    configs = [
        (build_calendar_server(),  8001),
        (build_task_server(),      8002),
        (build_notes_server(),     8003),
        (build_database_server(),  8004),
    ]

    servers = [
        uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info"))
        for app, port in configs
    ]

    await asyncio.gather(*[s.serve() for s in servers])


if __name__ == "__main__":
    asyncio.run(launch_all_servers())
