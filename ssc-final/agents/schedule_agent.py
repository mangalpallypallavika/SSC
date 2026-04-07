"""Schedule Agent - handles exam dates, subject calendars, daily study plans"""
from datetime import datetime, timedelta


SSC_SUBJECTS = [
    "Quantitative Aptitude",
    "English Language",
    "General Awareness",
    "Reasoning Ability",
    "Computer Knowledge"
]

DAILY_HOURS_MAP = {
    "light": 4,
    "moderate": 6,
    "intensive": 8
}


class ScheduleAgent:
    def __init__(self, db):
        self.db = db

    def handle(self, action: str, data: dict) -> dict:
        handlers = {
            "set_exam_date": self._set_exam_date,
            "get_schedule": self._get_schedule,
            "create_daily_plan": self._create_daily_plan,
            "get_subject_plan": self._get_subject_plan,
            "get_upcoming": self._get_upcoming,
        }
        handler = handlers.get(action)
        if not handler:
            return {"error": f"Unknown action: {action}"}
        return handler(data)

    def _set_exam_date(self, data: dict) -> dict:
        exam = {
            "exam_name": data.get("exam_name", "SSC CGL"),
            "exam_date": data.get("exam_date"),
            "tier": data.get("tier", "Tier-1"),
            "subjects": data.get("subjects", SSC_SUBJECTS),
            "notes": data.get("notes", ""),
            "created_at": datetime.now().isoformat()
        }
        exam_id = self.db.insert("exams", exam)
        
        # Calculate days remaining
        days_remaining = None
        if exam["exam_date"]:
            try:
                exam_dt = datetime.strptime(exam["exam_date"], "%Y-%m-%d")
                days_remaining = (exam_dt - datetime.now()).days
            except:
                pass
        
        return {
            "success": True,
            "exam_id": exam_id,
            "exam": exam,
            "days_remaining": days_remaining,
            "message": f"Exam '{exam['exam_name']}' scheduled for {exam['exam_date']}"
        }

    def _get_schedule(self, data: dict) -> dict:
        exams = self.db.query("exams", {})
        enriched = []
        for e in exams:
            item = dict(e)
            if item.get("exam_date"):
                try:
                    exam_dt = datetime.strptime(item["exam_date"], "%Y-%m-%d")
                    item["days_remaining"] = (exam_dt - datetime.now()).days
                    item["is_upcoming"] = item["days_remaining"] > 0
                except:
                    item["days_remaining"] = None
            enriched.append(item)
        enriched.sort(key=lambda x: x.get("exam_date") or "")
        return {"exams": enriched, "count": len(enriched)}

    def _create_daily_plan(self, data: dict) -> dict:
        study_mode = data.get("study_mode", "moderate")
        total_hours = DAILY_HOURS_MAP.get(study_mode, 6)
        start_date = data.get("start_date", datetime.now().strftime("%Y-%m-%d"))
        days = data.get("days", 7)
        subjects = data.get("subjects", SSC_SUBJECTS)
        
        # Allocate hours per subject (weighted)
        weights = {"Quantitative Aptitude": 2, "English Language": 1.5,
                   "General Awareness": 1, "Reasoning Ability": 2, "Computer Knowledge": 0.5}
        total_weight = sum(weights.get(s, 1) for s in subjects)
        
        plan = []
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        
        for day_num in range(days):
            current_date = start_dt + timedelta(days=day_num)
            day_subjects = subjects[day_num % len(subjects):] + subjects[:day_num % len(subjects)]
            primary = day_subjects[0]
            secondary = day_subjects[1] if len(day_subjects) > 1 else None
            
            primary_hours = round(total_hours * weights.get(primary, 1) / total_weight * 1.5, 1)
            secondary_hours = round(total_hours * 0.4, 1)
            revision_hours = round(total_hours - primary_hours - secondary_hours, 1)
            
            day_plan = {
                "date": current_date.strftime("%Y-%m-%d"),
                "day": current_date.strftime("%A"),
                "primary_subject": primary,
                "primary_hours": max(primary_hours, 1.5),
                "secondary_subject": secondary,
                "secondary_hours": max(secondary_hours, 1.0),
                "revision_hours": max(revision_hours, 0.5),
                "total_hours": total_hours,
                "study_mode": study_mode
            }
            plan.append(day_plan)
            self.db.insert("daily_plans", day_plan)
        
        return {"plan": plan, "days": days, "total_hours_per_day": total_hours, "study_mode": study_mode}

    def _get_subject_plan(self, data: dict) -> dict:
        subject = data.get("subject", "Quantitative Aptitude")
        subject_topics = {
            "Quantitative Aptitude": ["Number System", "Simplification", "Ratio & Proportion",
                "Percentage", "Profit & Loss", "SI & CI", "Time & Work", "Speed & Distance",
                "Geometry", "Mensuration", "Algebra", "Data Interpretation"],
            "English Language": ["Reading Comprehension", "Cloze Test", "Fill in the Blanks",
                "Error Detection", "Sentence Improvement", "Idioms & Phrases", "Synonyms/Antonyms",
                "One Word Substitution", "Active/Passive Voice", "Direct/Indirect Speech"],
            "General Awareness": ["History", "Geography", "Polity", "Economy", "Science & Technology",
                "Current Affairs", "Sports", "Awards & Honours", "Important Dates", "Books & Authors"],
            "Reasoning Ability": ["Series", "Analogy", "Classification", "Coding-Decoding",
                "Blood Relations", "Direction Sense", "Syllogism", "Matrix", "Statement & Conclusions",
                "Non-Verbal Reasoning"],
            "Computer Knowledge": ["Basics", "MS Office", "Internet", "Networking",
                "Operating Systems", "Database", "Security", "Shortcut Keys"]
        }
        
        topics = subject_topics.get(subject, ["Topic 1", "Topic 2"])
        plan = []
        for i, topic in enumerate(topics):
            plan.append({
                "week": (i // 3) + 1,
                "topic": topic,
                "suggested_hours": 3,
                "priority": "high" if i < 4 else "medium"
            })
        
        return {"subject": subject, "topics": plan, "total_topics": len(topics)}

    def _get_upcoming(self, data: dict) -> dict:
        exams = self.db.query("exams", {})
        upcoming = []
        for e in exams:
            if e.get("exam_date"):
                try:
                    exam_dt = datetime.strptime(e["exam_date"], "%Y-%m-%d")
                    days_rem = (exam_dt - datetime.now()).days
                    if days_rem >= 0:
                        e["days_remaining"] = days_rem
                        upcoming.append(e)
                except:
                    pass
        upcoming.sort(key=lambda x: x.get("exam_date", ""))
        return {"upcoming_exams": upcoming[:5], "count": len(upcoming)}
