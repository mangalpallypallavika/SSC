"""
api/main.py  —  FastAPI application entry point
Exposes the orchestrator as REST endpoints + health check.
Deploy this container to Cloud Run.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from mcp_servers.mcp_connect import MCPClient, MCPServerConfig, MCPServerType
from agents.orchestrator import OrchestratorAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Startup / shutdown
# ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Build MCP client from env vars (Cloud Run sets these)
    servers = [
        MCPServerConfig(
            MCPServerType.CALENDAR,
            os.getenv("CALENDAR_MCP_HOST", "localhost"),
            int(os.getenv("CALENDAR_MCP_PORT", "8001")),
            api_key=os.getenv("CALENDAR_MCP_KEY"),
        ),
        MCPServerConfig(
            MCPServerType.TASK_MANAGER,
            os.getenv("TASK_MCP_HOST", "localhost"),
            int(os.getenv("TASK_MCP_PORT", "8002")),
            api_key=os.getenv("TASK_MCP_KEY"),
        ),
        MCPServerConfig(
            MCPServerType.NOTES,
            os.getenv("NOTES_MCP_HOST", "localhost"),
            int(os.getenv("NOTES_MCP_PORT", "8003")),
            api_key=os.getenv("NOTES_MCP_KEY"),
        ),
        MCPServerConfig(
            MCPServerType.DATABASE,
            os.getenv("DB_MCP_HOST", "localhost"),
            int(os.getenv("DB_MCP_PORT", "8004")),
            api_key=os.getenv("DB_MCP_KEY"),
        ),
    ]

    mcp = MCPClient(servers)
    await mcp.connect_all()
    logger.info("MCP tools available: %s", mcp.list_tools())

    app.state.orchestrator = OrchestratorAgent(mcp)
    logger.info("Orchestrator ready.")

    yield
    # cleanup if needed


app = FastAPI(
    title="Multi-Agent AI System",
    description="Manages tasks, schedules, and information via ADK + MCP",
    version="1.0.0",
    lifespan=lifespan,
)


# ──────────────────────────────────────────────
#  Request / Response schemas
# ──────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = "default"


class ChatResponse(BaseModel):
    message: str
    agent:   Optional[str] = None
    intent:  Optional[str] = None
    data:    Optional[Dict[str, Any]] = None


# ──────────────────────────────────────────────
#  Endpoints
# ──────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/tools")
async def list_tools():
    """List all MCP tools discovered at startup."""
    orch: OrchestratorAgent = app.state.orchestrator
    return {"tools": orch.mcp.list_tools()}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Send a natural-language message to the orchestrator."""
    orch: OrchestratorAgent = app.state.orchestrator
    try:
        result = await orch.handle(req.message)
        return ChatResponse(**result)
    except Exception as exc:
        logger.exception("Orchestrator error")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/agent/{agent_name}/{intent}")
async def direct_invoke(agent_name: str, intent: str, params: Dict[str, Any] = {}):
    """Directly invoke a sub-agent by name + intent (for testing)."""
    orch: OrchestratorAgent = app.state.orchestrator
    agent = orch._agents.get(agent_name)
    if not agent:
        raise HTTPException(404, f"Agent '{agent_name}' not found")
    result = await agent.run(intent, params)
    return {"agent": agent_name, "intent": intent, "result": result}
