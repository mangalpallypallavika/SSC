"""YouTube Agent - manages educational YouTube links for SSC subjects"""
from datetime import datetime


RECOMMENDED_CHANNELS = {
    "Quantitative Aptitude": [
        {"channel": "Adda247", "url": "https://www.youtube.com/@Adda247", "topic": "Maths for SSC"},
        {"channel": "SSC Adda", "url": "https://www.youtube.com/@SSCAdda", "topic": "Quant shortcuts"},
    ],
    "English Language": [
        {"channel": "Neetu Singh English", "url": "https://www.youtube.com/@NeetuSinghEnglish", "topic": "English grammar"},
        {"channel": "KD Campus", "url": "https://www.youtube.com/@KDCampusOfficial", "topic": "English for SSC"},
    ],
    "General Awareness": [
        {"channel": "Study IQ", "url": "https://www.youtube.com/@StudyIQ", "topic": "Current affairs"},
        {"channel": "Gagan Pratap", "url": "https://www.youtube.com/@GaganPratapMaths", "topic": "GA for SSC"},
    ],
    "Reasoning Ability": [
        {"channel": "Reasoning by Deepak", "url": "https://www.youtube.com/@ReasoningByDeepa", "topic": "Reasoning tricks"},
        {"channel": "SSC Crackers", "url": "https://www.youtube.com/@SSCCrackers", "topic": "Reasoning for SSC"},
    ],
    "Computer Knowledge": [
        {"channel": "Learn Coding", "url": "https://www.youtube.com/@learncodingofficial", "topic": "Computer basics"},
    ]
}


class YouTubeAgent:
    def __init__(self, db):
        self.db = db

    def handle(self, action: str, data: dict) -> dict:
        handlers = {
            "save_link": self._save_link,
            "get_links": self._get_links,
            "search_links": self._search_links,
            "get_by_subject": self._get_by_subject,
        }
        handler = handlers.get(action)
        if not handler:
            return {"error": f"Unknown action: {action}"}
        return handler(data)

    def _save_link(self, data: dict) -> dict:
        link = {
            "title": data.get("title", "Untitled Video"),
            "url": data.get("url", ""),
            "subject": data.get("subject", "General"),
            "topic": data.get("topic", ""),
            "channel": data.get("channel", ""),
            "duration_minutes": data.get("duration_minutes"),
            "is_recommended": data.get("is_recommended", False),
            "notes": data.get("notes", ""),
            "saved_at": datetime.now().isoformat()
        }
        link_id = self.db.insert("youtube_links", link)
        return {"success": True, "link_id": link_id, "link": link,
                "message": f"Video '{link['title']}' saved successfully"}

    def _get_links(self, data: dict) -> dict:
        filters = {}
        if data.get("subject"):
            filters["subject"] = data["subject"]
        links = self.db.query("youtube_links", filters)
        links.sort(key=lambda x: x.get("saved_at", ""), reverse=True)
        return {"links": links, "count": len(links)}

    def _search_links(self, data: dict) -> dict:
        query = data.get("query", "").lower()
        all_links = self.db.query("youtube_links", {})
        results = [
            l for l in all_links
            if query in l.get("title", "").lower()
            or query in l.get("topic", "").lower()
            or query in l.get("subject", "").lower()
        ]
        
        # Also include recommended channels
        subject_recs = []
        for subject, recs in RECOMMENDED_CHANNELS.items():
            if query in subject.lower():
                for rec in recs:
                    subject_recs.append({**rec, "subject": subject, "is_recommended": True})
        
        return {"saved_links": results, "recommended": subject_recs, "count": len(results)}

    def _get_by_subject(self, data: dict) -> dict:
        subject = data.get("subject", "")
        saved = self.db.query("youtube_links", {"subject": subject})
        recommended = RECOMMENDED_CHANNELS.get(subject, [])
        return {
            "subject": subject,
            "saved_links": saved,
            "recommended_channels": recommended,
            "total_saved": len(saved)
        }
