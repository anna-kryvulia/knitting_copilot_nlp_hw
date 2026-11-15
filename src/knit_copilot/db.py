"""The only module that touches SQLite: stores projects as JSON documents.

Purpose: persistence for the project workflow (setup → locked versions → progress).
Input/Output: Project objects (knit_copilot.project). Model calls: none.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from contextlib import closing
from pathlib import Path

from knit_copilot.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    data TEXT NOT NULL,
    updated TEXT NOT NULL
);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or settings.db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute(SCHEMA)
    return con


def save(project, path: Path | None = None) -> None:
    with closing(connect(path)) as con, con:
        con.execute("INSERT INTO projects (id, name, data, updated) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(id) DO UPDATE SET name = excluded.name, data = excluded.data, updated = excluded.updated",
                    (project.id, project.name, project.model_dump_json(), dt.datetime.now().isoformat(timespec="seconds")))


def load(project_id: str, path: Path | None = None):
    from knit_copilot.project import Project
    with closing(connect(path)) as con:
        row = con.execute("SELECT data FROM projects WHERE id = ?", (project_id,)).fetchone()
    return Project.model_validate_json(row[0]) if row else None


def list_projects(path: Path | None = None) -> list[tuple[str, str, str]]:
    """(id, name, updated), newest first."""
    with closing(connect(path)) as con:
        return con.execute("SELECT id, name, updated FROM projects ORDER BY updated DESC").fetchall()
