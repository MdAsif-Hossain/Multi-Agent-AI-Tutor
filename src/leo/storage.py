from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import EvaluationReport, StudentProfile


class StudentMemory:
    """Small durable store for visible, per-student learning memory."""

    def __init__(self, path: str | Path = "data/leo.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_name TEXT NOT NULL COLLATE NOCASE,
                    topic TEXT NOT NULL,
                    level TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    score REAL NOT NULL,
                    mastered_concepts TEXT NOT NULL,
                    weak_concepts TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def save(
        self,
        profile: StudentProfile,
        topic: str,
        report: EvaluationReport,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sessions (
                    student_name, topic, level, goal, score,
                    mastered_concepts, weak_concepts
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile.name,
                    topic,
                    profile.level,
                    profile.goal,
                    report.score_percent,
                    json.dumps(report.mastered_concepts),
                    json.dumps(report.weak_concepts),
                ),
            )

    def recent(self, student_name: str, limit: int = 5) -> list[dict]:
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT topic, level, goal, score, mastered_concepts,
                       weak_concepts, created_at
                FROM sessions
                WHERE student_name = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (student_name, limit),
            ).fetchall()

        return [
            {
                **dict(row),
                "mastered_concepts": json.loads(row["mastered_concepts"]),
                "weak_concepts": json.loads(row["weak_concepts"]),
            }
            for row in rows
        ]

    def prompt_context(self, student_name: str) -> str:
        sessions = self.recent(student_name, limit=3)
        if not sessions:
            return "No previous learning sessions are stored for this student."
        return "\n".join(
            f"- Studied {session['topic']} at {session['level']} level; "
            f"score {session['score']:.0f}%; mastered: "
            f"{', '.join(session['mastered_concepts']) or 'not recorded'}; "
            f"weak concepts: {', '.join(session['weak_concepts']) or 'none'}."
            for session in sessions
        )
