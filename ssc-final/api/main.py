"""FastAPI Application - SSC Exam Scheduler Multi-Agent API"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List
import json
import os
import uuid
from datetime import datetime

from agents.orchestrator import orchestrate
from agents.task_agent import TaskAgent
from agents.schedule_agent import ScheduleAgent
from agents.notes_agent import NotesAgent
from agents.youtube_agent import YouTubeAgent
from db.database import Database

app = FastAPI(
    title="SSC Exam Scheduler - Multi-Agent AI System",
    description="AI-powered SSC exam preparation platform with multi-agent coordination",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

db = Database()

# ─── Request/Response Models ──────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    conversation_history: Optional[List[dict]] = None

class TaskCreate(BaseModel):
    title: str
    subject: Optional[str] = "General"
    priority: Optional[str] = "medium"
    due_date: Optional[str] = None
    description: Optional[str] = ""

class ExamCreate(BaseModel):
    exam_name: str
    exam_date: str
    tier: Optional[str] = "Tier-1"
    subjects: Optional[List[str]] = None
    notes: Optional[str] = ""

class NoteCreate(BaseModel):
    title: str
    content: str
    subject: Optional[str] = "General"
    topic: Optional[str] = ""
    is_important: Optional[bool] = False

class YouTubeLinkCreate(BaseModel):
    title: str
    url: str
    subject: Optional[str] = "General"
    topic: Optional[str] = ""
    channel: Optional[str] = ""

class DailyPlanRequest(BaseModel):
    study_mode: Optional[str] = "moderate"
    start_date: Optional[str] = None
    days: Optional[int] = 7
    subjects: Optional[List[str]] = None

# ─── Chat Endpoint (Main AI Interface) ───────────────────────────────────────

@app.post("/api/chat")
async def chat(request: ChatRequest):
    """Primary AI chat endpoint - routes through multi-agent orchestrator"""
    try:
        history = request.conversation_history or []
        result = orchestrate(request.message, history)
        
        # Save conversation
        session_id = request.session_id or str(uuid.uuid4())[:8]
        db.update("conversations", session_id, {
            "messages": json.dumps(result["conversation_history"][-10:]),
            "updated_at": datetime.now().isoformat()
        }) if db.get_by_id("conversations", session_id) else db.insert("conversations", {
            "session_id": session_id,
            "messages": json.dumps(result["conversation_history"][-10:]),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        })
        
        return {
            "response": result["response"],
            "session_id": session_id,
            "conversation_history": result["conversation_history"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─── Tasks API ────────────────────────────────────────────────────────────────

@app.get("/api/tasks")
async def list_tasks(subject: Optional[str] = None, status: Optional[str] = None):
    agent = TaskAgent(db)
    filters = {}
    if subject: filters["subject"] = subject
    if status: filters["status"] = status
    return agent.handle("list_tasks", filters)

@app.post("/api/tasks")
async def create_task(task: TaskCreate):
    agent = TaskAgent(db)
    return agent.handle("create_task", task.model_dump())

@app.patch("/api/tasks/{task_id}/complete")
async def complete_task(task_id: str):
    agent = TaskAgent(db)
    return agent.handle("complete_task", {"task_id": task_id})

@app.patch("/api/tasks/{task_id}")
async def update_task(task_id: str, updates: dict):
    agent = TaskAgent(db)
    return agent.handle("update_task", {"task_id": task_id, **updates})

@app.get("/api/tasks/stats")
async def task_stats():
    agent = TaskAgent(db)
    return agent.handle("get_stats", {})

# ─── Schedule / Exam API ──────────────────────────────────────────────────────

@app.get("/api/exams")
async def get_exams():
    agent = ScheduleAgent(db)
    return agent.handle("get_schedule", {})

@app.post("/api/exams")
async def create_exam(exam: ExamCreate):
    agent = ScheduleAgent(db)
    return agent.handle("set_exam_date", exam.model_dump())

@app.get("/api/exams/upcoming")
async def upcoming_exams():
    agent = ScheduleAgent(db)
    return agent.handle("get_upcoming", {})

@app.post("/api/schedule/daily-plan")
async def create_daily_plan(req: DailyPlanRequest):
    agent = ScheduleAgent(db)
    data = req.model_dump()
    if not data.get("start_date"):
        data["start_date"] = datetime.now().strftime("%Y-%m-%d")
    return agent.handle("create_daily_plan", data)

@app.get("/api/schedule/subject/{subject}")
async def get_subject_plan(subject: str):
    agent = ScheduleAgent(db)
    return agent.handle("get_subject_plan", {"subject": subject})

# ─── Notes API ────────────────────────────────────────────────────────────────

@app.get("/api/notes")
async def get_notes(subject: Optional[str] = None):
    agent = NotesAgent(db)
    return agent.handle("get_notes", {"subject": subject} if subject else {})

@app.post("/api/notes")
async def create_note(note: NoteCreate):
    agent = NotesAgent(db)
    return agent.handle("create_note", note.model_dump())

@app.get("/api/notes/search")
async def search_notes(q: str):
    agent = NotesAgent(db)
    return agent.handle("search_notes", {"query": q})

# ─── YouTube Links API ────────────────────────────────────────────────────────

@app.get("/api/youtube")
async def get_youtube_links(subject: Optional[str] = None):
    agent = YouTubeAgent(db)
    if subject:
        return agent.handle("get_by_subject", {"subject": subject})
    return agent.handle("get_links", {})

@app.post("/api/youtube")
async def save_youtube_link(link: YouTubeLinkCreate):
    agent = YouTubeAgent(db)
    return agent.handle("save_link", link.model_dump())

@app.get("/api/youtube/search")
async def search_youtube(q: str):
    agent = YouTubeAgent(db)
    return agent.handle("search_links", {"query": q})

# ─── Health & Info ────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "SSC Exam Scheduler", "version": "1.0.0"}

@app.get("/api/dashboard")
async def dashboard():
    """Get dashboard summary data"""
    task_agent = TaskAgent(db)
    schedule_agent = ScheduleAgent(db)
    
    task_stats = task_agent.handle("get_stats", {})
    upcoming = schedule_agent.handle("get_upcoming", {})
    recent_notes = NotesAgent(db).handle("get_notes", {})
    
    return {
        "tasks": task_stats,
        "upcoming_exams": upcoming["upcoming_exams"][:3],
        "recent_notes_count": recent_notes["count"],
        "last_updated": datetime.now().isoformat()
    }

# Serve frontend
if os.path.exists("frontend"):
    app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

@app.get("/")
async def serve_frontend():
    if os.path.exists("frontend/index.html"):
        return FileResponse("frontend/index.html")
    return {"message": "SSC Exam Scheduler API", "docs": "/docs"}
