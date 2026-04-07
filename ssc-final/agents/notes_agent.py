"""Notes Agent - handles study notes creation and retrieval"""
from datetime import datetime


class NotesAgent:
    def __init__(self, db):
        self.db = db

    def handle(self, action: str, data: dict) -> dict:
        handlers = {
            "create_note": self._create_note,
            "get_notes": self._get_notes,
            "search_notes": self._search_notes,
            "get_by_subject": self._get_by_subject,
        }
        handler = handlers.get(action)
        if not handler:
            return {"error": f"Unknown action: {action}"}
        return handler(data)

    def _create_note(self, data: dict) -> dict:
        note = {
            "title": data.get("title", "Untitled Note"),
            "content": data.get("content", ""),
            "subject": data.get("subject", "General"),
            "topic": data.get("topic", ""),
            "tags": data.get("tags", []),
            "is_important": data.get("is_important", False),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        note_id = self.db.insert("notes", note)
        return {"success": True, "note_id": note_id, "note": note,
                "message": f"Note '{note['title']}' saved successfully"}

    def _get_notes(self, data: dict) -> dict:
        filters = {}
        if data.get("subject"):
            filters["subject"] = data["subject"]
        notes = self.db.query("notes", filters)
        notes.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return {"notes": notes[:20], "count": len(notes)}

    def _search_notes(self, data: dict) -> dict:
        query = data.get("query", "").lower()
        all_notes = self.db.query("notes", {})
        results = [
            n for n in all_notes
            if query in n.get("title", "").lower()
            or query in n.get("content", "").lower()
            or query in n.get("topic", "").lower()
        ]
        return {"notes": results[:10], "count": len(results), "query": query}

    def _get_by_subject(self, data: dict) -> dict:
        subject = data.get("subject", "")
        notes = self.db.query("notes", {"subject": subject})
        important = [n for n in notes if n.get("is_important")]
        return {"subject": subject, "notes": notes, "important_notes": important,
                "count": len(notes)}
