# SSC Exam Scheduler — Multi-Agent AI System

A fully functional multi-agent AI system for SSC exam preparation, deployable on Google Cloud Run.

## Architecture

```
User → FastAPI (Port 8080)
         ↓
    Orchestrator Agent (Claude claude-sonnet-4-20250514)
    ┌────────┬──────────┬─────────┬──────────┐
    ▼        ▼          ▼         ▼
TaskAgent  ScheduleAgent  NotesAgent  YouTubeAgent
    └────────┴──────────┴─────────┴──────────┘
                     ↓
              SQLite Database
```

## Features

| Feature | Description |
|---------|-------------|
| 💬 AI Chat | Natural language interface via multi-agent orchestration |
| ✅ Tasks | Create, track, complete study tasks with priorities |
| 📅 Schedule | Set exam dates, generate daily study timetables |
| 📝 Notes | Save formulas, concepts, important points |
| ▶️ YouTube | Store and retrieve educational video links |
| 📊 Dashboard | Progress overview, stats, upcoming exams |

## SSC Subjects Covered

- Quantitative Aptitude
- English Language  
- General Awareness
- Reasoning Ability
- Computer Knowledge

## Quick Start (Local)

```bash
# Install dependencies
pip install -r requirements.txt

# Set your Anthropic API key
export ANTHROPIC_API_KEY="your-key-here"

# Run the server
uvicorn api.main:app --reload --port 8000

# Open in browser
open http://localhost:8000
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/chat` | AI chat (main orchestrator) |
| GET/POST | `/api/tasks` | Task management |
| GET/POST | `/api/exams` | Exam scheduling |
| POST | `/api/schedule/daily-plan` | Generate study plan |
| GET/POST | `/api/notes` | Study notes |
| GET/POST | `/api/youtube` | YouTube links |
| GET | `/api/dashboard` | Dashboard summary |
| GET | `/health` | Health check |

## Deploy to Google Cloud Run

### Prerequisites
- Google Cloud account with billing enabled
- `gcloud` CLI installed
- Anthropic API key

### Steps

1. **Edit `deploy.sh`** — set your Project ID and API key:
   ```bash
   PROJECT_ID="my-gcp-project"
   ANTHROPIC_API_KEY="sk-ant-..."
   ```

2. **Run deployment:**
   ```bash
   chmod +x deploy.sh
   ./deploy.sh
   ```

3. **Done!** You'll get a public URL like:
   ```
   https://ssc-exam-scheduler-xxxx-el.a.run.app
   ```

### GCP Services Used

| Service | Purpose | Cost |
|---------|---------|------|
| Cloud Run | Serverless container hosting | ~Free (first 2M req/month) |
| Cloud Build | Docker image building | ~Free (120 min/day) |
| Container Registry | Image storage | ~$0.10/GB/month |
| Secret Manager | Secure API key storage | ~Free (first 6 secrets) |

**Estimated cost: < $5/month** for moderate usage.

## Example AI Interactions

```
User: "Create a 7-day study plan for SSC CGL Tier-1"
→ Orchestrator calls ScheduleAgent.create_daily_plan()
→ Returns detailed day-by-day schedule

User: "I finished the Percentage chapter. Mark it done."
→ Orchestrator calls TaskAgent.complete_task()
→ Updates task status to completed

User: "Save note: Compound Interest = P(1+R/100)^T - P"
→ Orchestrator calls NotesAgent.create_note()
→ Saves formula with subject tagging

User: "Find YouTube videos for Reasoning"
→ Orchestrator calls YouTubeAgent.get_by_subject()
→ Returns saved + recommended channels
```

## File Structure

```
ssc-scheduler/
├── agents/
│   ├── orchestrator.py    # Primary agent (Claude claude-sonnet-4-20250514)
│   ├── task_agent.py      # Task management sub-agent
│   ├── schedule_agent.py  # Schedule & exam sub-agent
│   ├── notes_agent.py     # Notes sub-agent
│   └── youtube_agent.py   # YouTube links sub-agent
├── api/
│   └── main.py            # FastAPI application
├── db/
│   └── database.py        # SQLite database layer
├── frontend/
│   └── index.html         # Full-stack UI
├── Dockerfile             # Container config
├── deploy.sh              # Cloud Run deployment
└── requirements.txt       # Python dependencies
```
