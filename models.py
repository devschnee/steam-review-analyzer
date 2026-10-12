"""Pydantic models for the optional FastAPI backend."""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

Sentiment = Literal["POSITIVE", "NEGATIVE", "NEUTRAL", "MIXED"]


class HealthResponse(BaseModel):
    status: str = Field(..., examples=["running"])
    service: str = Field(..., examples=["Steam Review Analyzer API"])
    version: str = Field(..., examples=["2.0.0"])
    docs_url: str = Field(..., examples=["/docs"])


class ReviewCreate(BaseModel):
    content: str = Field(..., min_length=2, max_length=4000, description="리뷰 본문")
    app_id: str = Field(default="manual", min_length=1, max_length=40, description="Steam App ID")
    game_id: Optional[str] = Field(default=None, description="게임 식별자. 기본값은 app_id")
    game_name: Optional[str] = Field(default="Manual Input", max_length=160, description="게임명")
    author: Optional[str] = Field(default="steam_user", max_length=120, description="작성자")
    playtime_hours: Optional[float] = Field(default=0, ge=0, description="플레이 시간")
    recommended: Optional[bool] = Field(default=True, description="Steam 추천 여부")
    language: Optional[str] = Field(default="koreana", description="리뷰 언어")
    created_at: Optional[str] = Field(default=None, description="원본 작성일")


class ReviewResponse(BaseModel):
    id: int
    app_id: str
    game_id: str
    game_name: str
    source_review_id: Optional[str] = None
    language: Optional[str] = None
    content: str
    author: Optional[str] = None
    playtime_hours: Optional[float] = None
    recommended: Optional[bool] = None
    created_at: Optional[str] = None
    inserted_at: str


class AnalyzeRequest(BaseModel):
    review_id: int = Field(..., ge=1, description="분석할 리뷰 ID")
    force_reanalyze: bool = Field(default=False, description="기존 분석 결과가 있어도 재분석할지 여부")


class SteamCollectRequest(BaseModel):
    app_id_or_url: str = Field(..., min_length=3, description="Steam App ID 또는 상점 URL")
    language: str = Field(default="koreana", description="Steam 리뷰 언어")
    max_reviews: int = Field(default=100, ge=20, le=500, description="수집할 최대 리뷰 수")


class SteamAnalyzeRequest(BaseModel):
    app_id: str = Field(..., min_length=1, description="분석할 Steam App ID")
    analyze_count: int = Field(default=30, ge=1, le=100, description="최신 리뷰 중 분석할 개수")
    force_reanalyze: bool = Field(default=False, description="기존 분석 결과가 있어도 재분석할지 여부")


class AnalysisResponse(BaseModel):
    id: int
    review_id: int
    sentiment: Sentiment
    confidence: float = Field(..., ge=0, le=1)
    topic: str
    keywords: List[str]
    summary: str
    aspect_graphics: str
    aspect_gameplay: str
    aspect_story: str
    aspect_performance: str
    aspect_value: str
    aspect_multiplayer: str
    source: str
    analyzed_at: str


class ReviewWithAnalysisResponse(BaseModel):
    review_id: int
    app_id: str
    game_id: str
    game_name: str
    language: Optional[str] = None
    content: str
    author: Optional[str] = None
    playtime_hours: Optional[float] = None
    recommended: Optional[bool] = None
    created_at: Optional[str] = None
    sentiment: Optional[Sentiment] = None
    confidence: Optional[float] = None
    topic: Optional[str] = None
    keywords: Optional[List[str]] = None
    summary: Optional[str] = None
    source: Optional[str] = None
    analyzed_at: Optional[str] = None


class StatsResponse(BaseModel):
    total_reviews: int
    analyzed_count: int
    recommended_rate: float
    average_playtime_hours: float
    average_confidence: float
    sentiment_distribution: Dict[str, int]
    topic_distribution: Dict[str, int]
