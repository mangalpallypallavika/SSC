"""Database layer - SQLite for structured data storage"""
import sqlite3
import json
import uuid
import os
from contextlib import contextmanager


DB_PATH = os.environ.get("DB_PATH", "ssc_scheduler.db")


class Database:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or DB_PATH
        self._init_tables()

    @contextmanager
    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_tables(self):
        tables = {
            "tasks": """
                id TEXT PRIMARY KEY,
                title TEXT, subject TEXT, priority TEXT,
                due_date TEXT, description TEXT, status TEXT,
                created_at TEXT, updated_at TEXT, completed_at TEXT
            """,
            "exams": """
                id TEXT PRIMARY KEY,
                exam_name TEXT, exam_date TEXT, tier TEXT,
                subjects TEXT, notes TEXT, created_at TEXT
            """,
            "daily_plans": """
                id TEXT PRIMARY KEY,
                date TEXT, day TEXT, primary_subject TEXT,
                primary_hours REAL, secondary_subject TEXT,
                secondary_hours REAL, revision_hours REAL,
                total_hours REAL, study_mode TEXT
            """,
            "notes": """
                id TEXT PRIMARY KEY,
                title TEXT, content TEXT, subject TEXT,
                topic TEXT, tags TEXT, is_important INTEGER,
                created_at TEXT, updated_at TEXT
            """,
            "youtube_links": """
                id TEXT PRIMARY KEY,
                title TEXT, url TEXT, subject TEXT,
                topic TEXT, channel TEXT, duration_minutes INTEGER,
                is_recommended INTEGER, notes TEXT, saved_at TEXT
            """,
            "conversations": """
                id TEXT PRIMARY KEY,
                session_id TEXT, messages TEXT, created_at TEXT, updated_at TEXT
            """
        }
        with self._get_conn() as conn:
            for table, schema in tables.items():
                conn.execute(f"CREATE TABLE IF NOT EXISTS {table} ({schema})")

    def insert(self, table: str, data: dict) -> str:
        record_id = str(uuid.uuid4())[:8]
        data = dict(data)
        data["id"] = record_id
        
        # Serialize lists/dicts to JSON strings
        for k, v in data.items():
            if isinstance(v, (list, dict)):
                data[k] = json.dumps(v)
            elif isinstance(v, bool):
                data[k] = int(v)
        
        cols = ", ".join(data.keys())
        placeholders = ", ".join(["?" for _ in data])
        with self._get_conn() as conn:
            conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
                        list(data.values()))
        return record_id

    def query(self, table: str, filters: dict) -> list:
        where = ""
        params = []
        if filters:
            conditions = [f"{k} = ?" for k in filters]
            where = "WHERE " + " AND ".join(conditions)
            params = list(filters.values())
        
        with self._get_conn() as conn:
            rows = conn.execute(f"SELECT * FROM {table} {where}", params).fetchall()
        
        results = []
        for row in rows:
            item = dict(row)
            # Deserialize JSON strings back to Python objects
            for k, v in item.items():
                if isinstance(v, str) and (v.startswith("[") or v.startswith("{")):
                    try:
                        item[k] = json.loads(v)
                    except:
                        pass
            results.append(item)
        return results

    def update(self, table: str, record_id: str, updates: dict) -> bool:
        for k, v in updates.items():
            if isinstance(v, (list, dict)):
                updates[k] = json.dumps(v)
            elif isinstance(v, bool):
                updates[k] = int(v)
        
        set_clause = ", ".join([f"{k} = ?" for k in updates])
        params = list(updates.values()) + [record_id]
        with self._get_conn() as conn:
            result = conn.execute(f"UPDATE {table} SET {set_clause} WHERE id = ?", params)
            return result.rowcount > 0

    def delete(self, table: str, record_id: str) -> bool:
        with self._get_conn() as conn:
            result = conn.execute(f"DELETE FROM {table} WHERE id = ?", [record_id])
            return result.rowcount > 0

    def get_by_id(self, table: str, record_id: str) -> dict | None:
        with self._get_conn() as conn:
            row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", [record_id]).fetchone()
        if not row:
            return None
        item = dict(row)
        for k, v in item.items():
            if isinstance(v, str) and (v.startswith("[") or v.startswith("{")):
                try:
                    item[k] = json.loads(v)
                except:
                    pass
        return item
