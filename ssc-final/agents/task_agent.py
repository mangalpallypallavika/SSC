"""Task Agent - handles study task management"""
from datetime import datetime


class TaskAgent:
    def __init__(self, db):
        self.db = db

    def handle(self, action: str, data: dict) -> dict:
        handlers = {
            "create_task": self._create_task,
            "list_tasks": self._list_tasks,
            "update_task": self._update_task,
            "complete_task": self._complete_task,
            "get_stats": self._get_stats,
        }
        handler = handlers.get(action)
        if not handler:
            return {"error": f"Unknown action: {action}"}
        return handler(data)

    def _create_task(self, data: dict) -> dict:
        task = {
            "title": data.get("title", "Untitled Task"),
            "subject": data.get("subject", "General"),
            "priority": data.get("priority", "medium"),
            "due_date": data.get("due_date"),
            "description": data.get("description", ""),
            "status": "pending",
            "created_at": datetime.now().isoformat()
        }
        task_id = self.db.insert("tasks", task)
        return {"success": True, "task_id": task_id, "task": task, "message": f"Task '{task['title']}' created successfully"}

    def _list_tasks(self, data: dict) -> dict:
        filters = {}
        if data.get("subject"):
            filters["subject"] = data["subject"]
        if data.get("status"):
            filters["status"] = data["status"]
        tasks = self.db.query("tasks", filters)
        return {"tasks": tasks, "count": len(tasks)}

    def _update_task(self, data: dict) -> dict:
        task_id = data.get("task_id")
        updates = {k: v for k, v in data.items() if k != "task_id"}
        updates["updated_at"] = datetime.now().isoformat()
        success = self.db.update("tasks", task_id, updates)
        return {"success": success, "message": "Task updated" if success else "Task not found"}

    def _complete_task(self, data: dict) -> dict:
        task_id = data.get("task_id")
        success = self.db.update("tasks", task_id, {
            "status": "completed",
            "completed_at": datetime.now().isoformat()
        })
        return {"success": success, "message": "Task marked complete!" if success else "Task not found"}

    def _get_stats(self, data: dict) -> dict:
        all_tasks = self.db.query("tasks", {})
        total = len(all_tasks)
        completed = sum(1 for t in all_tasks if t.get("status") == "completed")
        pending = sum(1 for t in all_tasks if t.get("status") == "pending")
        by_subject = {}
        for t in all_tasks:
            s = t.get("subject", "General")
            by_subject[s] = by_subject.get(s, 0) + 1
        return {
            "total": total,
            "completed": completed,
            "pending": pending,
            "completion_rate": round((completed / total * 100) if total > 0 else 0, 1),
            "by_subject": by_subject
        }
