"""Steam review collection utilities.

This module collects public Steam reviews by App ID. It does not require a
Steam Web API key because it uses the public appreviews endpoint.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import requests

STEAM_REVIEW_ENDPOINT = "https://store.steampowered.com/appreviews/{app_id}"
STEAM_APPDETAILS_ENDPOINT = "https://store.steampowered.com/api/appdetails"

SUPPORTED_LANGUAGES = {
    "koreana": "한국어",
    "english": "영어",
    "japanese": "일본어",
    "schinese": "중국어 간체",
    "tchinese": "중국어 번체",
    "spanish": "스페인어",
    "german": "독일어",
    "french": "프랑스어",
}


def parse_steam_app_id(value: str) -> str:
    """Extract Steam App ID from either a raw number or a Steam store URL."""
    text = (value or "").strip()
    if not text:
        raise ValueError("Steam App ID 또는 Steam 상점 URL을 입력하세요.")

    if text.isdigit():
        return text

    match = re.search(r"/app/(\d+)", text)
    if match:
        return match.group(1)

    # Fallback: first long numeric token inside pasted text.
    match = re.search(r"\b(\d{3,})\b", text)
    if match:
        return match.group(1)

    raise ValueError("Steam App ID를 찾지 못했습니다. 예: 268910 또는 https://store.steampowered.com/app/268910")


def get_app_details(app_id: str, country: str = "KR", language: str = "koreana") -> dict[str, Any]:
    """Fetch basic Steam app metadata. Returns a minimal fallback on failure."""
    try:
        response = requests.get(
            STEAM_APPDETAILS_ENDPOINT,
            params={"appids": app_id, "cc": country, "l": language},
            timeout=15,
            headers={"User-Agent": "SteamReviewAnalyzer/1.0"},
        )
        response.raise_for_status()
        payload = response.json().get(str(app_id), {})
        if payload.get("success") and isinstance(payload.get("data"), dict):
            data = payload["data"]
            return {
                "app_id": app_id,
                "name": data.get("name") or f"Steam App {app_id}",
                "type": data.get("type"),
                "short_description": data.get("short_description"),
                "header_image": data.get("header_image"),
                "steam_url": f"https://store.steampowered.com/app/{app_id}",
            }
    except Exception:
        pass

    return {
        "app_id": app_id,
        "name": f"Steam App {app_id}",
        "type": None,
        "short_description": None,
        "header_image": None,
        "steam_url": f"https://store.steampowered.com/app/{app_id}",
    }


def _normalize_review(app_id: str, game_name: str, language: str, review: dict[str, Any]) -> dict[str, Any]:
    author = review.get("author") or {}
    created_ts = review.get("timestamp_created") or review.get("timestamp_updated")
    if created_ts:
        created_at = datetime.fromtimestamp(int(created_ts), tz=timezone.utc).isoformat()
    else:
        created_at = None

    playtime_minutes = author.get("playtime_forever") or 0
    try:
        playtime_hours = round(float(playtime_minutes) / 60, 2)
    except Exception:
        playtime_hours = 0.0

    return {
        "source_review_id": str(review.get("recommendationid") or ""),
        "app_id": str(app_id),
        "game_id": str(app_id),
        "game_name": game_name,
        "language": language,
        "content": (review.get("review") or "").strip(),
        "author": str(author.get("steamid") or "steam_user"),
        "playtime_hours": playtime_hours,
        "recommended": bool(review.get("voted_up")),
        "created_at": created_at,
        "votes_up": int(review.get("votes_up") or 0),
        "weighted_vote_score": float(review.get("weighted_vote_score") or 0),
    }


def fetch_steam_reviews(
    app_id: str,
    language: str = "koreana",
    max_reviews: int = 100,
    filter_mode: str = "recent",
    purchase_type: str = "all",
    sleep_seconds: float = 0.2,
) -> dict[str, Any]:
    """Collect up to max_reviews reviews from Steam public reviews endpoint."""
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"지원하지 않는 언어입니다: {language}")

    max_reviews = max(1, min(int(max_reviews), 500))
    app_id = parse_steam_app_id(app_id)
    app_info = get_app_details(app_id, language=language)
    game_name = app_info["name"]

    reviews: list[dict[str, Any]] = []
    cursor = "*"
    seen_ids: set[str] = set()

    while len(reviews) < max_reviews:
        per_page = min(100, max_reviews - len(reviews))
        params = {
            "json": 1,
            "language": language,
            "filter": filter_mode,
            "purchase_type": purchase_type,
            "num_per_page": per_page,
            "cursor": cursor,
        }

        response = requests.get(
            STEAM_REVIEW_ENDPOINT.format(app_id=quote(app_id)),
            params=params,
            timeout=20,
            headers={"User-Agent": "SteamReviewAnalyzer/1.0"},
        )
        response.raise_for_status()
        payload = response.json()

        batch = payload.get("reviews") or []
        if not batch:
            break

        for item in batch:
            normalized = _normalize_review(app_id, game_name, language, item)
            if not normalized["content"]:
                continue
            if normalized["source_review_id"] in seen_ids:
                continue
            seen_ids.add(normalized["source_review_id"])
            reviews.append(normalized)
            if len(reviews) >= max_reviews:
                break

        next_cursor = payload.get("cursor")
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor
        time.sleep(sleep_seconds)

    return {
        "app_info": app_info,
        "language": language,
        "requested_count": max_reviews,
        "collected_count": len(reviews),
        "reviews": reviews,
    }
