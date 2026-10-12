"""Generic Steam review analyzer with Groq-first and fallback behavior."""

from __future__ import annotations

import json
import os
import re
from typing import Any

POSITIVE_WORDS = [
    "재밌", "재미", "추천", "강추", "최고", "갓겜", "좋", "명작", "성취감", "완벽",
    "만족", "훌륭", "재구매", "계속", "몰입", "감동", "친구", "힐링", "따뜻", "웃기", "시원", "협동", "꾸준", "새벽", "인생", "awesome", "great", "good",
    "fun", "recommend", "love", "masterpiece", "best",
]
NEGATIVE_WORDS = [
    "별로", "최악", "환불", "아깝", "짜증", "스트레스", "포기", "비추천", "버그", "실망",
    "피로", "불친절", "렉", "튕", "과금", "매칭", "핵", "밸런스", "서버", "오류", "답답", "지루", "못 느꼈", "부담", "불안정", "멘탈", "못 하게", "crash", "bug",
    "boring", "refund", "bad", "worst", "broken", "lag", "toxic",
]
GRAPHICS_WORDS = ["그래픽", "아트", "작화", "애니", "그림", "음악", "사운드", "ost", "visual", "music", "art"]
GAMEPLAY_WORDS = ["난이도", "보스", "패턴", "컨트롤", "조작", "플레이", "전투", "빌드", "매칭", "멀티", "gameplay", "combat"]
VALUE_WORDS = ["가격", "세일", "돈", "환불", "가성비", "dlc", "과금", "price", "sale", "worth"]
PERFORMANCE_WORDS = ["버그", "튕", "렉", "프레임", "최적화", "서버", "crash", "bug", "lag", "fps", "server"]
STORY_WORDS = ["스토리", "서사", "캐릭터", "엔딩", "연출", "story", "character", "ending"]


def _extract_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def _count_matches(text: str, words: list[str]) -> int:
    return sum(1 for word in words if word.lower() in text)


def _unique(values: list[str]) -> list[str]:
    result = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def fallback_analyze_review(content: str, game_name: str | None = None) -> dict[str, Any]:
    """Deterministic local analyzer for no-key review environments."""
    text = (content or "").lower()
    pos = _count_matches(text, POSITIVE_WORDS)
    neg = _count_matches(text, NEGATIVE_WORDS)

    mixed_markers = ["좋지만", "재밌긴", "재밌지만", "추천은 하지만", "아쉽", "다만", "but", "however", "mixed"]
    neutral_markers = ["그냥", "보통", "평범", "아직", "모르", "무난", "soso", "okay", "average"]
    sarcasm_or_warning = ["저혈압", "혈압", "암걸", "사람 미치", "다시는", "하지 마", "do not buy"]

    strong_negative_markers = ["추천하기 어렵", "환불", "제대로 플레이하기 어렵", "못 느꼈", "실망", "지루", "답답", "불친절", "멘탈 나감", "게임을 못 하게"]

    if any(marker in text for marker in sarcasm_or_warning):
        sentiment = "NEGATIVE"
        confidence = 0.82
    elif any(marker in text for marker in strong_negative_markers):
        sentiment = "NEGATIVE"
        confidence = 0.80
    elif any(marker in text for marker in mixed_markers) or (pos > 0 and neg > 0):
        sentiment = "MIXED"
        confidence = 0.74
    elif any(marker in text for marker in neutral_markers):
        sentiment = "NEUTRAL"
        confidence = 0.68
    elif pos > neg:
        sentiment = "POSITIVE"
        confidence = min(0.95, 0.62 + pos * 0.08)
    elif neg > pos:
        sentiment = "NEGATIVE"
        confidence = min(0.95, 0.62 + neg * 0.08)
    else:
        sentiment = "NEUTRAL"
        confidence = 0.55

    topic_scores = {
        "gameplay": _count_matches(text, GAMEPLAY_WORDS),
        "graphics_audio": _count_matches(text, GRAPHICS_WORDS),
        "performance": _count_matches(text, PERFORMANCE_WORDS),
        "value": _count_matches(text, VALUE_WORDS),
        "story": _count_matches(text, STORY_WORDS),
    }
    topic = max(topic_scores, key=topic_scores.get)
    if topic_scores[topic] == 0:
        topic = "general"

    matched_keywords = []
    for words in [GAMEPLAY_WORDS, GRAPHICS_WORDS, PERFORMANCE_WORDS, VALUE_WORDS, STORY_WORDS, POSITIVE_WORDS, NEGATIVE_WORDS]:
        matched_keywords.extend([word for word in words if word.lower() in text])
    keywords = _unique(matched_keywords)[:6]

    game_label = game_name or "해당 게임"
    if sentiment == "POSITIVE":
        summary = f"{game_label}에 대해 재미, 완성도 또는 추천 의사가 긍정적으로 드러난 리뷰입니다."
    elif sentiment == "NEGATIVE":
        summary = f"{game_label}에 대해 버그, 피로감, 비용, 밸런스 등 불만이 드러난 리뷰입니다."
    elif sentiment == "MIXED":
        summary = f"{game_label}에 대해 장점과 단점이 함께 나타나는 복합 감정 리뷰입니다."
    else:
        summary = f"{game_label}에 대한 강한 긍정 또는 부정 판단이 어려운 리뷰입니다."

    return {
        "sentiment": sentiment,
        "confidence": round(float(confidence), 2),
        "topic": topic,
        "keywords": keywords,
        "summary": summary,
        "aspect_graphics": "POSITIVE" if topic == "graphics_audio" and sentiment != "NEGATIVE" else ("NEGATIVE" if topic == "graphics_audio" else "NOT_MENTIONED"),
        "aspect_gameplay": sentiment if topic == "gameplay" else "NOT_MENTIONED",
        "aspect_story": sentiment if topic == "story" else "NOT_MENTIONED",
        "aspect_performance": "NEGATIVE" if topic == "performance" else "NOT_MENTIONED",
        "aspect_value": sentiment if topic == "value" else "NOT_MENTIONED",
        "aspect_multiplayer": sentiment if any(word in text for word in ["멀티", "매칭", "친구", "co-op", "coop", "multiplayer"]) else "NOT_MENTIONED",
        "source": "fallback_rule_based",
    }


def analyze_review(content: str, game_name: str | None = None) -> dict[str, Any]:
    """Analyze one review using Groq when configured, otherwise fallback."""
    api_key = os.getenv("GROQ_API_KEY")
    model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    fallback = fallback_analyze_review(content, game_name=game_name)

    if not api_key:
        return fallback

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
        prompt = f"""
게임명: {game_name or '알 수 없음'}
아래 Steam 리뷰를 분석하세요.

출력은 JSON 객체 하나만 허용합니다.
필드:
- sentiment: POSITIVE / NEGATIVE / NEUTRAL / MIXED 중 하나
- confidence: 0.0~1.0 숫자
- topic: gameplay / graphics_audio / performance / value / story / multiplayer / general 중 하나
- keywords: 핵심 키워드 문자열 배열, 최대 6개
- summary: 한국어 한 문장 요약
- aspect_graphics, aspect_gameplay, aspect_story, aspect_performance, aspect_value, aspect_multiplayer: POSITIVE/NEGATIVE/NEUTRAL/MIXED/NOT_MENTIONED 중 하나

주의:
- 추천한다는 표현이 있어도 조건부 추천이면 MIXED 또는 NEUTRAL로 판단합니다.
- AI의 confidence는 정확도와 다를 수 있으므로 과도하게 높게 주지 마세요.
- 짧은 리뷰나 농담/반어법은 문맥 기준으로 보수적으로 판단하세요.

리뷰:
{content[:2000]}
""".strip()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "너는 Steam 게임 리뷰를 분석하는 품질 분석 엔진이다. JSON만 출력한다."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=500,
        )
        raw = response.choices[0].message.content or "{}"
        result = _extract_json(raw)
        fallback.update(
            {
                "sentiment": str(result.get("sentiment", fallback["sentiment"])).upper(),
                "confidence": max(0.0, min(1.0, float(result.get("confidence", fallback["confidence"])))),
                "topic": str(result.get("topic", fallback["topic"])),
                "keywords": result.get("keywords", fallback["keywords"]),
                "summary": str(result.get("summary", fallback["summary"])),
                "aspect_graphics": str(result.get("aspect_graphics", fallback["aspect_graphics"])),
                "aspect_gameplay": str(result.get("aspect_gameplay", fallback["aspect_gameplay"])),
                "aspect_story": str(result.get("aspect_story", fallback["aspect_story"])),
                "aspect_performance": str(result.get("aspect_performance", fallback["aspect_performance"])),
                "aspect_value": str(result.get("aspect_value", fallback["aspect_value"])),
                "aspect_multiplayer": str(result.get("aspect_multiplayer", fallback["aspect_multiplayer"])),
                "source": "groq",
            }
        )
        if not isinstance(fallback["keywords"], list):
            fallback["keywords"] = [str(fallback["keywords"])]
        return fallback
    except Exception as exc:
        fallback["source"] = f"fallback_after_llm_error:{type(exc).__name__}"
        return fallback
