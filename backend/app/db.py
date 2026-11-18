from __future__ import annotations

import json
import sqlite3
import time
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Iterator, Optional

from .schemas import ChordsPayload, LyricsPayload, SkipSegment

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"
DB_PATH = CACHE_DIR / "fretflow.db"


@contextmanager
def _db_conn() -> Iterator[sqlite3.Connection]:
    """Context manager that both commits transactions AND closes the SQLite FD."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    with closing(conn), conn:
        yield conn


def init_db() -> None:
    with _db_conn() as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS song_sessions (
                video_id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT '',
                artist TEXT NOT NULL DEFAULT '',
                album TEXT NOT NULL DEFAULT '',
                duration_sec INTEGER NOT NULL DEFAULT 0,
                thumbnail_url TEXT NOT NULL DEFAULT '',
                auto_offset_ms INTEGER NOT NULL DEFAULT 0,
                manual_offset_ms INTEGER NOT NULL DEFAULT 0,
                skip_segments_json TEXT NOT NULL DEFAULT '[]',
                lyrics_json TEXT,
                chords_fast_json TEXT,
                chords_neural_json TEXT,
                updated_at REAL NOT NULL
            )
            """
        )


def get_cached_session(video_id: str) -> Optional[dict]:
    with _db_conn() as conn:
        row = conn.execute(
            "SELECT * FROM song_sessions WHERE video_id = ?", (video_id,)
        ).fetchone()
        return dict(row) if row else None


def upsert_metadata_and_lyrics(
    video_id: str,
    title: str,
    artist: str,
    album: str,
    duration_sec: int,
    thumbnail_url: str,
    auto_offset_ms: int,
    skip_segments: list[SkipSegment],
    lyrics: Optional[LyricsPayload],
) -> int:
    """Save metadata + lyrics and return persisted manual_offset_ms."""
    skip_json = json.dumps([s.model_dump() for s in skip_segments])
    lyrics_json = lyrics.model_dump_json() if lyrics else None
    now = time.time()

    with _db_conn() as conn:
        existing = conn.execute(
            "SELECT manual_offset_ms FROM song_sessions WHERE video_id = ?",
            (video_id,),
        ).fetchone()
        manual_offset_ms = int(existing["manual_offset_ms"]) if existing else 0

        conn.execute(
            """
            INSERT INTO song_sessions (
                video_id, title, artist, album, duration_sec, thumbnail_url,
                auto_offset_ms, manual_offset_ms, skip_segments_json, lyrics_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(video_id) DO UPDATE SET
                title = CASE WHEN excluded.title != '' THEN excluded.title ELSE song_sessions.title END,
                artist = CASE WHEN excluded.artist != '' THEN excluded.artist ELSE song_sessions.artist END,
                album = CASE WHEN excluded.album != '' THEN excluded.album ELSE song_sessions.album END,
                duration_sec = CASE WHEN excluded.duration_sec > 0 THEN excluded.duration_sec ELSE song_sessions.duration_sec END,
                thumbnail_url = CASE WHEN excluded.thumbnail_url != '' THEN excluded.thumbnail_url ELSE song_sessions.thumbnail_url END,
                auto_offset_ms = excluded.auto_offset_ms,
                skip_segments_json = excluded.skip_segments_json,
                lyrics_json = COALESCE(excluded.lyrics_json, song_sessions.lyrics_json),
                updated_at = excluded.updated_at
            """,
            (
                video_id,
                title,
                artist,
                album,
                max(0, int(duration_sec)),
                thumbnail_url,
                int(auto_offset_ms),
                manual_offset_ms,
                skip_json,
                lyrics_json,
                now,
            ),
        )
        return manual_offset_ms


def save_chords_payload(
    video_id: str, chords: ChordsPayload, duration_sec: int = 0
) -> None:
    col = (
        "chords_neural_json"
        if chords.engine == "neural_btc_170"
        else "chords_fast_json"
    )
    now = time.time()
    with _db_conn() as conn:
        conn.execute(
            f"""
            INSERT INTO song_sessions (video_id, duration_sec, {col}, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(video_id) DO UPDATE SET
                duration_sec = CASE WHEN excluded.duration_sec > 0 THEN excluded.duration_sec ELSE song_sessions.duration_sec END,
                {col} = excluded.{col},
                updated_at = excluded.updated_at
            """,
            (video_id, max(0, int(duration_sec)), chords.model_dump_json(), now),
        )


def update_manual_offset(video_id: str, manual_offset_ms: int) -> bool:
    """Update manual_offset_ms only if session exists; returns True if updated."""
    now = time.time()
    with _db_conn() as conn:
        cur = conn.execute(
            "UPDATE song_sessions SET manual_offset_ms = ?, updated_at = ? WHERE video_id = ?",
            (int(manual_offset_ms), now, video_id),
        )
        return cur.rowcount > 0


def delete_session_if_no_chords(video_id: str) -> None:
    with _db_conn() as conn:
        conn.execute(
            "DELETE FROM song_sessions WHERE video_id = ? AND chords_fast_json IS NULL AND chords_neural_json IS NULL",
            (video_id,),
        )
