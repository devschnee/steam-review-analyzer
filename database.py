"""SQLite database layer for the deployable Steam review analyzer."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Optional

DEFAULT_DB_PATH = os.getenv("DB_PATH", "steam_review_analyzer.db")


def get_db_path() -> str:
    return os.getenv("DB_PATH", DEFAULT_DB_PATH)


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _json_list(value: Any) -> str:
    if value is None:
        return "[]"
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return "[]"
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return json.dumps(parsed, ensure_ascii=False)
        except Exception:
            pass
        return json.dumps([x.strip() for x in text.split(",") if x.strip()], ensure_ascii=False)
    return json.dumps([str(value)], ensure_ascii=False)


def parse_keywords(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
        except Exception:
            pass
        return [x.strip() for x in text.split(",") if x.strip()]
    return [str(value)]


def row_to_dict(row: Optional[sqlite3.Row]) -> Optional[dict[str, Any]]:
    return dict(row) if row is not None else None


def normalize_review(row: dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    if data.get("recommended") is not None:
        data["recommended"] = bool(data["recommended"])
    return data


def normalize_analysis(row: dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    data["keywords"] = parse_keywords(data.get("keywords"))
    return data


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_id TEXT NOT NULL,
                game_id TEXT NOT NULL,
                game_name TEXT NOT NULL DEFAULT 'Unknown Game',
                source_review_id TEXT,
                language TEXT DEFAULT 'koreana',
                content TEXT NOT NULL CHECK (length(trim(content)) >= 2),
                author TEXT DEFAULT 'steam_user',
                playtime_hours REAL DEFAULT 0 CHECK (playtime_hours >= 0),
                recommended INTEGER CHECK (recommended IN (0, 1)),
                votes_up INTEGER DEFAULT 0,
                weighted_vote_score REAL DEFAULT 0,
                created_at TEXT,
                inserted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(app_id, source_review_id)
            );

            CREATE TABLE IF NOT EXISTS analysis_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                review_id INTEGER NOT NULL,
                sentiment TEXT NOT NULL CHECK (sentiment IN ('POSITIVE', 'NEGATIVE', 'NEUTRAL', 'MIXED')),
                confidence REAL NOT NULL DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),
                topic TEXT DEFAULT 'general',
                keywords TEXT DEFAULT '[]',
                summary TEXT DEFAULT '',
                aspect_graphics TEXT DEFAULT 'NOT_MENTIONED',
                aspect_gameplay TEXT DEFAULT 'NOT_MENTIONED',
                aspect_story TEXT DEFAULT 'NOT_MENTIONED',
                aspect_performance TEXT DEFAULT 'NOT_MENTIONED',
                aspect_value TEXT DEFAULT 'NOT_MENTIONED',
                aspect_multiplayer TEXT DEFAULT 'NOT_MENTIONED',
                source TEXT NOT NULL DEFAULT 'fallback_rule_based',
                analyzed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (review_id) REFERENCES reviews(id) ON DELETE CASCADE,
                UNIQUE(review_id)
            );

            CREATE INDEX IF NOT EXISTS idx_reviews_app_id ON reviews(app_id);
            CREATE INDEX IF NOT EXISTS idx_reviews_game_id ON reviews(game_id);
            CREATE INDEX IF NOT EXISTS idx_reviews_recommended ON reviews(recommended);
            CREATE INDEX IF NOT EXISTS idx_reviews_language ON reviews(language);
            CREATE INDEX IF NOT EXISTS idx_analysis_sentiment ON analysis_results(sentiment);
            CREATE INDEX IF NOT EXISTS idx_analysis_topic ON analysis_results(topic);
            CREATE INDEX IF NOT EXISTS idx_analysis_confidence ON analysis_results(confidence);
            """
        )
        conn.commit()


def create_review(
    content: str,
    app_id: str = "manual",
    game_id: str | None = None,
    game_name: str = "Manual Input",
    author: str | None = "steam_user",
    playtime_hours: float | None = 0,
    recommended: bool | None = True,
    language: str = "koreana",
    created_at: str | None = None,
    source_review_id: str | None = None,
    votes_up: int | None = 0,
    weighted_vote_score: float | None = 0,
) -> dict[str, Any]:
    if not content or not content.strip():
        raise ValueError("content must not be empty")
    if len(content.strip()) < 2:
        raise ValueError("content must be at least 2 characters")
    init_db()
    now = datetime.utcnow().isoformat(timespec="seconds")
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO reviews (
                app_id, game_id, game_name, source_review_id, language, content,
                author, playtime_hours, recommended, votes_up, weighted_vote_score,
                created_at, inserted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(app_id),
                str(game_id or app_id),
                game_name or f"Steam App {app_id}",
                source_review_id,
                language,
                content.strip(),
                author or "steam_user",
                float(playtime_hours or 0),
                None if recommended is None else (1 if bool(recommended) else 0),
                int(votes_up or 0),
                float(weighted_vote_score or 0),
                created_at or now,
                now,
            ),
        )
        conn.commit()
        if cursor.lastrowid:
            created_id = cursor.lastrowid
        else:
            row = conn.execute(
                "SELECT id FROM reviews WHERE app_id = ? AND source_review_id = ?",
                (str(app_id), source_review_id),
            ).fetchone()
            created_id = row["id"] if row else None
    if created_id is None:
        raise RuntimeError("failed to create or find review")
    created = get_review(created_id)
    assert created is not None
    return created


def bulk_save_steam_reviews(reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Save Steam reviews defensively.

    Steam reviews can contain empty strings, one-character reactions, or duplicates.
    A single bad row should not make the whole collection step fail, so this
    function skips invalid rows and continues saving the rest.
    """
    saved = []
    skipped_count = 0

    for review in reviews:
        content = (review.get("content") or "").strip()
        if len(content) < 2:
            skipped_count += 1
            continue

        try:
            saved.append(
                create_review(
                    app_id=review.get("app_id") or review.get("game_id"),
                    game_id=review.get("game_id") or review.get("app_id"),
                    game_name=review.get("game_name") or f"Steam App {review.get('app_id')}",
                    source_review_id=review.get("source_review_id"),
                    language=review.get("language") or "koreana",
                    content=content,
                    author=review.get("author") or "steam_user",
                    playtime_hours=review.get("playtime_hours") or 0,
                    recommended=review.get("recommended"),
                    votes_up=review.get("votes_up") or 0,
                    weighted_vote_score=review.get("weighted_vote_score") or 0,
                    created_at=review.get("created_at"),
                )
            )
        except Exception:
            # Keep collection robust: duplicate/invalid rows should not abort all saves.
            skipped_count += 1
            continue

    return saved


def get_review(review_id: int) -> Optional[dict[str, Any]]:
    init_db()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM reviews WHERE id = ?", (review_id,)).fetchone()
    data = row_to_dict(row)
    return normalize_review(data) if data else None


def get_all_reviews(
    limit: int = 50,
    offset: int = 0,
    sentiment: str | None = None,
    app_id: str | None = None,
    language: str | None = None,
) -> list[dict[str, Any]]:
    init_db()
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    joins: list[str] = []
    where: list[str] = []
    params: list[Any] = []

    if sentiment and sentiment != "ALL":
        joins.append("JOIN analysis_results a ON r.id = a.review_id")
        where.append("a.sentiment = ?")
        params.append(sentiment.upper())
    if app_id:
        where.append("r.app_id = ?")
        params.append(str(app_id))
    if language:
        where.append("r.language = ?")
        params.append(language)

    query = "SELECT r.* FROM reviews r "
    if joins:
        query += " ".join(joins) + " "
    if where:
        query += "WHERE " + " AND ".join(where) + " "
    query += "ORDER BY COALESCE(r.created_at, r.inserted_at) DESC, r.id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with get_connection() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    return [normalize_review(dict(row)) for row in rows]


def save_analysis(review_id: int, analysis: dict[str, Any]) -> dict[str, Any]:
    init_db()
    now = datetime.utcnow().isoformat(timespec="seconds")
    sentiment = str(analysis.get("sentiment", "NEUTRAL")).upper()
    if sentiment not in {"POSITIVE", "NEGATIVE", "NEUTRAL", "MIXED"}:
        sentiment = "NEUTRAL"
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO analysis_results (
                review_id, sentiment, confidence, topic, keywords, summary,
                aspect_graphics, aspect_gameplay, aspect_story, aspect_performance,
                aspect_value, aspect_multiplayer, source, analyzed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                review_id,
                sentiment,
                max(0.0, min(1.0, float(analysis.get("confidence", 0.5)))),
                analysis.get("topic", "general"),
                _json_list(analysis.get("keywords", [])),
                analysis.get("summary", ""),
                analysis.get("aspect_graphics", "NOT_MENTIONED"),
                analysis.get("aspect_gameplay", "NOT_MENTIONED"),
                analysis.get("aspect_story", "NOT_MENTIONED"),
                analysis.get("aspect_performance", "NOT_MENTIONED"),
                analysis.get("aspect_value", "NOT_MENTIONED"),
                analysis.get("aspect_multiplayer", "NOT_MENTIONED"),
                analysis.get("source", "fallback_rule_based"),
                now,
            ),
        )
        conn.commit()
    saved = get_analysis(review_id)
    assert saved is not None
    return saved


def get_analysis(review_id: int) -> Optional[dict[str, Any]]:
    init_db()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM analysis_results WHERE review_id = ?", (review_id,)).fetchone()
    data = row_to_dict(row)
    return normalize_analysis(data) if data else None


def get_review_with_analysis(review_id: int) -> Optional[dict[str, Any]]:
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                r.id AS review_id,
                r.app_id,
                r.game_id,
                r.game_name,
                r.language,
                r.content,
                r.author,
                r.playtime_hours,
                r.recommended,
                r.created_at,
                a.sentiment,
                a.confidence,
                a.topic,
                a.keywords,
                a.summary,
                a.source,
                a.analyzed_at
            FROM reviews r
            LEFT JOIN analysis_results a ON r.id = a.review_id
            WHERE r.id = ?
            """,
            (review_id,),
        ).fetchone()
    data = row_to_dict(row)
    if not data:
        return None
    data["recommended"] = bool(data["recommended"]) if data.get("recommended") is not None else None
    data["keywords"] = parse_keywords(data.get("keywords"))
    return data


def get_joined_reviews(app_id: str | None = None, sentiment: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    init_db()
    where: list[str] = []
    params: list[Any] = []
    if app_id:
        where.append("r.app_id = ?")
        params.append(str(app_id))
    if sentiment and sentiment != "ALL":
        where.append("a.sentiment = ?")
        params.append(sentiment.upper())
    query = """
        SELECT
            r.id AS review_id, r.app_id, r.game_name, r.language, r.content, r.author,
            r.playtime_hours, r.recommended, r.created_at,
            a.sentiment, a.confidence, a.topic, a.keywords, a.summary, a.source, a.analyzed_at
        FROM reviews r
        LEFT JOIN analysis_results a ON r.id = a.review_id
    """
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY COALESCE(r.created_at, r.inserted_at) DESC, r.id DESC LIMIT ?"
    params.append(max(1, min(int(limit), 500)))
    with get_connection() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    data = []
    for row in rows:
        item = dict(row)
        item["recommended"] = bool(item["recommended"]) if item.get("recommended") is not None else None
        item["keywords"] = parse_keywords(item.get("keywords"))
        data.append(item)
    return data


def get_stats(app_id: str | None = None) -> dict[str, Any]:
    init_db()
    review_where = "WHERE app_id = ?" if app_id else ""
    review_params = (str(app_id),) if app_id else ()
    analysis_join_where = "WHERE r.app_id = ?" if app_id else ""
    analysis_params = (str(app_id),) if app_id else ()

    with get_connection() as conn:
        total_reviews = conn.execute(f"SELECT COUNT(*) FROM reviews {review_where}", review_params).fetchone()[0]
        recommended_count = conn.execute(
            f"SELECT COUNT(*) FROM reviews {review_where + (' AND' if review_where else 'WHERE')} recommended = 1",
            review_params,
        ).fetchone()[0] if total_reviews else 0
        avg_playtime = conn.execute(f"SELECT AVG(playtime_hours) FROM reviews {review_where}", review_params).fetchone()[0] or 0
        analyzed_count = conn.execute(
            f"SELECT COUNT(*) FROM analysis_results a JOIN reviews r ON a.review_id = r.id {analysis_join_where}",
            analysis_params,
        ).fetchone()[0]
        avg_confidence = conn.execute(
            f"SELECT AVG(a.confidence) FROM analysis_results a JOIN reviews r ON a.review_id = r.id {analysis_join_where}",
            analysis_params,
        ).fetchone()[0] or 0
        sentiment_rows = conn.execute(
            f"""
            SELECT a.sentiment, COUNT(*) AS count
            FROM analysis_results a JOIN reviews r ON a.review_id = r.id
            {analysis_join_where}
            GROUP BY a.sentiment ORDER BY count DESC
            """,
            analysis_params,
        ).fetchall()
        topic_rows = conn.execute(
            f"""
            SELECT a.topic, COUNT(*) AS count
            FROM analysis_results a JOIN reviews r ON a.review_id = r.id
            {analysis_join_where}
            GROUP BY a.topic ORDER BY count DESC LIMIT 10
            """,
            analysis_params,
        ).fetchall()

    sentiment_distribution = {row["sentiment"]: row["count"] for row in sentiment_rows}
    topic_distribution = {row["topic"]: row["count"] for row in topic_rows}
    recommended_rate = (recommended_count / total_reviews * 100) if total_reviews else 0
    return {
        "total_reviews": int(total_reviews),
        "analyzed_count": int(analyzed_count),
        "recommended_rate": round(float(recommended_rate), 2),
        "average_playtime_hours": round(float(avg_playtime), 2),
        "average_confidence": round(float(avg_confidence), 3),
        "sentiment_distribution": sentiment_distribution,
        "topic_distribution": topic_distribution,
    }


def binary_expected_sentiment(recommended: bool | None) -> str | None:
    if recommended is None:
        return None
    return "POSITIVE" if bool(recommended) else "NEGATIVE"


def is_binary_correct(ai_sentiment: str | None, recommended: bool | None) -> bool | None:
    """Compare AI sentiment with Steam recommended as a binary compatibility check.

    Steam recommended is binary, while the AI can output NEUTRAL/MIXED.
    NEUTRAL/MIXED are treated as ambiguous rather than automatically wrong.
    High-confidence risk cases are therefore reserved for direct contradictions:
    POSITIVE vs not recommended, or NEGATIVE vs recommended.
    """
    expected = binary_expected_sentiment(recommended)
    if expected is None or not ai_sentiment:
        return None
    sentiment = ai_sentiment.upper()
    if sentiment not in {"POSITIVE", "NEGATIVE"}:
        return None
    return sentiment == expected


def get_validation_frame(app_id: str | None = None) -> list[dict[str, Any]]:
    rows = get_joined_reviews(app_id=app_id, limit=500)
    result = []
    for item in rows:
        if not item.get("sentiment"):
            continue
        expected = binary_expected_sentiment(item.get("recommended"))
        correct = is_binary_correct(item.get("sentiment"), item.get("recommended"))
        result.append(
            {
                **item,
                "expected_sentiment_from_steam_recommended": expected,
                "is_binary_correct": correct,
                "is_high_confidence": (item.get("confidence") or 0) >= 0.85,
                "is_high_confidence_wrong": bool((item.get("confidence") or 0) >= 0.85 and correct is False),
            }
        )
    return result
