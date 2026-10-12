"""Optional FastAPI backend for Steam Review Analyzer.

The public Streamlit deployment can run with app.py alone. This backend remains
available for local DB/API/UI integration and Swagger testing.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, status

from analyzer import analyze_review
from database import (
    bulk_save_steam_reviews,
    create_review,
    get_all_reviews,
    get_analysis,
    get_joined_reviews,
    get_review,
    get_review_with_analysis,
    get_stats,
    init_db,
    save_analysis,
)
from models import (
    AnalysisResponse,
    AnalyzeRequest,
    HealthResponse,
    ReviewCreate,
    ReviewResponse,
    ReviewWithAnalysisResponse,
    StatsResponse,
    SteamAnalyzeRequest,
    SteamCollectRequest,
)
from steam_client import fetch_steam_reviews, parse_steam_app_id

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Steam Review Analyzer API",
    description=(
        "Steam App ID를 입력해 공개 리뷰를 수집하고, SQLite 저장, LLM/fallback 분석, "
        "통계 조회를 제공하는 범용 게임 리뷰 분석 API입니다."
    ),
    version="2.0.0",
    lifespan=lifespan,
)


@app.get("/", response_model=HealthResponse, tags=["health"])
def health_check() -> dict:
    return {
        "status": "running",
        "service": "Steam Review Analyzer API",
        "version": "2.0.0",
        "docs_url": "/docs",
    }


@app.get("/reviews", response_model=List[ReviewResponse], tags=["reviews"])
def list_reviews(
    limit: int = Query(default=20, ge=1, le=500, description="조회할 리뷰 개수"),
    offset: int = Query(default=0, ge=0, description="건너뛸 리뷰 개수"),
    sentiment: Optional[str] = Query(default=None, description="감성 필터: POSITIVE/NEGATIVE/NEUTRAL/MIXED"),
    app_id: Optional[str] = Query(default=None, description="Steam App ID 필터"),
    language: Optional[str] = Query(default=None, description="리뷰 언어 필터"),
) -> list[dict]:
    return get_all_reviews(limit=limit, offset=offset, sentiment=sentiment, app_id=app_id, language=language)


@app.get("/reviews/{review_id}", response_model=ReviewWithAnalysisResponse, tags=["reviews"])
def read_review(review_id: int) -> dict:
    review = get_review_with_analysis(review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="리뷰를 찾을 수 없습니다.")
    return review


@app.post("/reviews", response_model=ReviewResponse, status_code=status.HTTP_201_CREATED, tags=["reviews"])
def add_review(review: ReviewCreate) -> dict:
    try:
        return create_review(
            app_id=review.app_id,
            game_id=review.game_id,
            game_name=review.game_name or "Manual Input",
            content=review.content,
            author=review.author,
            playtime_hours=review.playtime_hours,
            recommended=review.recommended,
            language=review.language or "koreana",
            created_at=review.created_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/steam/collect", tags=["steam"])
def collect_steam_reviews(request: SteamCollectRequest) -> dict:
    try:
        payload = fetch_steam_reviews(
            request.app_id_or_url,
            language=request.language,
            max_reviews=request.max_reviews,
        )
        saved = bulk_save_steam_reviews(payload["reviews"])
        return {
            "app_info": payload["app_info"],
            "language": payload["language"],
            "collected_count": payload["collected_count"],
            "saved_count": len(saved),
            "min_review_warning": payload["collected_count"] < 20,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Steam 리뷰 수집 중 오류가 발생했습니다: {exc}") from exc


@app.post("/analyze", response_model=AnalysisResponse, tags=["analysis"])
def analyze_existing_review(request: AnalyzeRequest) -> dict:
    review = get_review(request.review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="분석할 리뷰를 찾을 수 없습니다.")

    existing = get_analysis(request.review_id)
    if existing and not request.force_reanalyze:
        return existing

    try:
        result = analyze_review(review["content"], game_name=review.get("game_name"))
        return save_analysis(request.review_id, result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"분석 중 오류가 발생했습니다: {exc}") from exc


@app.post("/steam/analyze", tags=["analysis"])
def analyze_recent_steam_reviews(request: SteamAnalyzeRequest) -> dict:
    app_id = parse_steam_app_id(request.app_id)
    reviews = get_all_reviews(limit=request.analyze_count, offset=0, app_id=app_id)
    if len(reviews) < 1:
        raise HTTPException(status_code=404, detail="해당 App ID로 저장된 리뷰가 없습니다. 먼저 /steam/collect를 실행하세요.")

    analyzed = []
    for review in reviews[: request.analyze_count]:
        existing = get_analysis(review["id"])
        if existing and not request.force_reanalyze:
            analyzed.append(existing)
            continue
        result = analyze_review(review["content"], game_name=review.get("game_name"))
        analyzed.append(save_analysis(review["id"], result))

    return {"app_id": app_id, "requested_count": request.analyze_count, "analyzed_count": len(analyzed), "results": analyzed}


@app.get("/analysis/{review_id}", response_model=AnalysisResponse, tags=["analysis"])
def read_analysis(review_id: int) -> dict:
    result = get_analysis(review_id)
    if result is None:
        raise HTTPException(status_code=404, detail="분석 결과를 찾을 수 없습니다.")
    return result


@app.get("/stats", response_model=StatsResponse, tags=["stats"])
def stats(app_id: Optional[str] = Query(default=None, description="Steam App ID별 통계")) -> dict:
    return get_stats(app_id=app_id)


@app.get("/validation", tags=["validation"])
def validation_rows(app_id: Optional[str] = Query(default=None, description="Steam App ID별 검증 결과")) -> list[dict]:
    from database import get_validation_frame

    return get_validation_frame(app_id=app_id)
