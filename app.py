"""Deployable Streamlit web app for Steam review collection and analysis."""

from __future__ import annotations

import os
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

from analyzer import analyze_review
from database import (
    bulk_save_steam_reviews,
    get_joined_reviews,
    get_stats,
    get_validation_frame,
    init_db,
    save_analysis,
)
from steam_client import SUPPORTED_LANGUAGES, fetch_steam_reviews, parse_steam_app_id

load_dotenv()

# Streamlit Cloud secrets -> environment variables.
try:
    if "GROQ_API_KEY" in st.secrets and not os.getenv("GROQ_API_KEY"):
        os.environ["GROQ_API_KEY"] = st.secrets["GROQ_API_KEY"]
    if "GROQ_MODEL" in st.secrets and not os.getenv("GROQ_MODEL"):
        os.environ["GROQ_MODEL"] = st.secrets["GROQ_MODEL"]
    if "DB_PATH" in st.secrets and not os.getenv("DB_PATH"):
        os.environ["DB_PATH"] = st.secrets["DB_PATH"]
except Exception:
    pass

st.set_page_config(
    page_title="Steam Review Analyzer",
    page_icon="🎮",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
.block-container {padding-top: 1.4rem; padding-bottom: 2rem;}
.metric-card {border: 1px solid #e8e8ee; border-radius: 16px; padding: 16px; background: #ffffff;}
.small-muted {color: #6b7280; font-size: 0.9rem;}
.badge {display: inline-block; border-radius: 999px; padding: 3px 10px; font-weight: 700; font-size: 0.85rem;}
.badge-high {background: #DCFCE7; color: #166534;}
.badge-mid {background: #FEF3C7; color: #92400E;}
.badge-low {background: #FEE2E2; color: #991B1B;}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def confidence_badge(confidence: float | None) -> str:
    value = float(confidence or 0)
    if value >= 0.90:
        return "🟢 높음"
    if value >= 0.75:
        return "🟡 보통"
    return "🔴 주의"


def ai_matches_steam(sentiment: str | None, recommended: bool | None) -> bool | None:
    if sentiment is None or recommended is None:
        return None
    expected = "POSITIVE" if recommended else "NEGATIVE"
    return sentiment == expected


def to_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if "keywords" in df.columns:
        df["keywords"] = df["keywords"].apply(lambda x: ", ".join(x) if isinstance(x, list) else x)
    if "confidence" in df.columns:
        df["confidence_pct"] = (pd.to_numeric(df["confidence"], errors="coerce").fillna(0) * 100).round(1)
        df["confidence_badge"] = df["confidence"].apply(confidence_badge)
    if "recommended" in df.columns:
        df["steam_recommended"] = df["recommended"].map({True: "추천", False: "비추천"})
    if {"sentiment", "recommended"}.issubset(df.columns):
        df["steam_expected"] = df["recommended"].apply(lambda v: "POSITIVE" if v is True else ("NEGATIVE" if v is False else None))
        df["binary_correct"] = df.apply(lambda row: ai_matches_steam(row.get("sentiment"), row.get("recommended")), axis=1)
        df["high_confidence_wrong"] = (df["confidence"].fillna(0) >= 0.85) & (df["binary_correct"] == False)
    return df


def render_metric_card(label: str, value: str, help_text: str = "") -> None:
    st.metric(label, value, help=help_text or None)


@st.cache_data(show_spinner=False, ttl=600)
def cached_fetch(app_id_or_url: str, language: str, max_reviews: int) -> dict[str, Any]:
    return fetch_steam_reviews(app_id_or_url, language=language, max_reviews=max_reviews)


init_db()

st.title("🎮 Steam 리뷰 분석 웹앱")
st.caption("Steam App ID 또는 상점 URL을 입력하면 공개 리뷰를 수집하고, 최신 리뷰 일부를 LLM/fallback으로 분석합니다.")

with st.sidebar:
    st.header("분석 설정")
    app_input = st.text_input(
        "Steam App ID 또는 URL",
        value=st.session_state.get("app_input", "268910"),
        help="예: 268910 또는 https://store.steampowered.com/app/268910/Cuphead/",
    )
    language = st.selectbox(
        "리뷰 언어",
        options=list(SUPPORTED_LANGUAGES.keys()),
        format_func=lambda key: f"{SUPPORTED_LANGUAGES[key]} ({key})",
        index=0,
    )
    max_reviews = st.slider("수집할 리뷰 수", min_value=20, max_value=200, value=100, step=10)
    analyze_count = st.slider("AI 분석 리뷰 수", min_value=10, max_value=50, value=30, step=5)
    min_reviews = st.number_input("권장 최소 리뷰 수", min_value=5, max_value=100, value=20, step=5)
    allow_small_sample = st.checkbox("권장 기준 미만이어도 분석 진행", value=True)
    force_reanalyze = st.checkbox("기존 분석이 있어도 재분석", value=False)
    sentiment_filter = st.selectbox("표시 감성 필터", options=["ALL", "POSITIVE", "NEGATIVE", "NEUTRAL", "MIXED"], index=0)
    display_count = st.slider("표시 리뷰 수", min_value=5, max_value=100, value=30, step=5)
    st.divider()
    st.caption("GROQ_API_KEY가 없으면 fallback 규칙 기반 분석으로 동작합니다.")
    st.caption("② 분석 버튼만 눌러도 DB 리뷰가 부족하면 Steam에서 먼저 자동 수집합니다.")

col_collect, col_analyze, col_sample = st.columns([1, 1, 1])

with col_collect:
    collect_clicked = st.button("① Steam 리뷰 수집", type="primary", use_container_width=True)
with col_analyze:
    analyze_clicked = st.button("② 최신 리뷰 분석", use_container_width=True)
with col_sample:
    try:
        link_app_id = parse_steam_app_id(app_input)
    except Exception:
        link_app_id = "268910"
    st.link_button("Steam 상점 열기", f"https://store.steampowered.com/app/{link_app_id}", use_container_width=True)

if collect_clicked:
    try:
        app_id = parse_steam_app_id(app_input)
        st.session_state["app_input"] = app_input
        with st.spinner("Steam 공개 리뷰를 수집하는 중..."):
            payload = cached_fetch(app_input, language, max_reviews)
            saved_reviews = bulk_save_steam_reviews(payload["reviews"])
        st.session_state["current_app_id"] = app_id
        st.session_state["current_app_info"] = payload["app_info"]
        st.session_state["collected_count"] = payload["collected_count"]
        st.success(f"{payload['app_info']['name']} 리뷰 {payload['collected_count']}개 수집 / DB 저장 {len(saved_reviews)}개 완료")
        if payload["collected_count"] < min_reviews:
            st.warning(f"수집된 리뷰가 {payload['collected_count']}개입니다. 권장 최소 기준 {min_reviews}개 미만이므로 분석 신뢰도가 낮을 수 있습니다.")
    except Exception as exc:
        st.error(f"리뷰 수집 실패: {exc}")

app_id_for_view = None
try:
    app_id_for_view = parse_steam_app_id(app_input)
except Exception:
    app_id_for_view = st.session_state.get("current_app_id")

if analyze_clicked:
    try:
        app_id = parse_steam_app_id(app_input)
        st.session_state["app_input"] = app_input

        rows = get_joined_reviews(app_id=app_id, limit=max_reviews)

        # 사용자가 ② 분석 버튼부터 눌러도 막히지 않도록, DB 리뷰가 부족하면 먼저 자동 수집합니다.
        if len(rows) < min_reviews:
            with st.spinner("DB 리뷰가 부족해서 Steam 리뷰를 먼저 자동 수집하는 중..."):
                payload = cached_fetch(app_input, language, max_reviews)
                saved_reviews = bulk_save_steam_reviews(payload["reviews"])
            st.session_state["current_app_id"] = app_id
            st.session_state["current_app_info"] = payload["app_info"]
            st.session_state["collected_count"] = payload["collected_count"]
            st.info(
                f"DB 기존 {len(rows)}개 → Steam에서 {payload['collected_count']}개 수집 "
                f"/ DB 저장 {len(saved_reviews)}개 완료"
            )
            rows = get_joined_reviews(app_id=app_id, limit=max_reviews)

        if not rows:
            st.error("분석할 리뷰가 없습니다. App ID/URL 또는 리뷰 언어를 확인해주세요.")
        elif len(rows) < min_reviews and not allow_small_sample:
            st.warning(
                f"DB에 저장된 리뷰가 {len(rows)}개입니다. 권장 최소 기준 {min_reviews}개 미만이므로 "
                "분석을 중단했습니다. 기준을 낮추거나 '권장 기준 미만이어도 분석 진행'을 체크해주세요."
            )
        else:
            if len(rows) < min_reviews:
                st.warning(
                    f"DB에 저장된 리뷰가 {len(rows)}개입니다. 권장 최소 기준 {min_reviews}개보다 적어 "
                    "통계 신뢰도는 낮을 수 있지만, 사용자가 선택한 설정에 따라 분석을 진행합니다."
                )

            targets = rows[: min(analyze_count, len(rows))]
            progress = st.progress(0)
            analyzed_count = 0
            skipped_count = 0

            for i, review in enumerate(targets, start=1):
                if review.get("sentiment") and not force_reanalyze:
                    skipped_count += 1
                    progress.progress(i / len(targets))
                    continue
                result = analyze_review(review["content"], game_name=review.get("game_name"))
                save_analysis(review["review_id"], result)
                analyzed_count += 1
                progress.progress(i / len(targets))

            st.session_state["current_app_id"] = app_id
            st.success(f"최신 리뷰 {len(targets)}개 확인 완료 / 신규 분석 {analyzed_count}개 / 기존 결과 재사용 {skipped_count}개")
    except Exception as exc:
        st.error(f"분석 실패: {exc}")

if app_id_for_view:
    stats = get_stats(app_id=app_id_for_view)
    rows = get_joined_reviews(app_id=app_id_for_view, sentiment=sentiment_filter, limit=display_count)
else:
    stats = get_stats()
    rows = get_joined_reviews(sentiment=sentiment_filter, limit=display_count)

df = to_dataframe(rows)
validation_rows = get_validation_frame(app_id=app_id_for_view) if app_id_for_view else get_validation_frame()
validation_df = to_dataframe(validation_rows)

app_info = st.session_state.get("current_app_info")
if app_info:
    info_cols = st.columns([1, 4])
    with info_cols[0]:
        if app_info.get("header_image"):
            st.image(app_info["header_image"], use_container_width=True)
    with info_cols[1]:
        st.subheader(app_info.get("name", f"Steam App {app_id_for_view}"))
        st.caption(app_info.get("steam_url"))
        if app_info.get("short_description"):
            st.write(app_info["short_description"])

m1, m2, m3, m4 = st.columns(4)
positive = int(stats.get("sentiment_distribution", {}).get("POSITIVE", 0))
negative = int(stats.get("sentiment_distribution", {}).get("NEGATIVE", 0))
neutral = int(stats.get("sentiment_distribution", {}).get("NEUTRAL", 0))
mixed = int(stats.get("sentiment_distribution", {}).get("MIXED", 0))
analyzed = int(stats.get("analyzed_count", 0))
pos_rate = (positive / analyzed * 100) if analyzed else 0
risk_count = int(validation_df["high_confidence_wrong"].sum()) if not validation_df.empty and "high_confidence_wrong" in validation_df.columns else 0

with m1:
    render_metric_card("총 리뷰 수", f"{stats.get('total_reviews', 0):,}", "DB에 저장된 리뷰 수")
with m2:
    render_metric_card("긍정 비율", f"{pos_rate:.1f}%", "AI 분석 결과 중 POSITIVE 비율")
with m3:
    render_metric_card("부정 수", f"{negative:,}", "AI 분석 결과 중 NEGATIVE 수")
with m4:
    render_metric_card("위험 케이스", f"{risk_count:,}", "신뢰도 85% 이상인데 Steam 추천 여부와 어긋난 사례")

st.divider()

tab_dashboard, tab_reviews, tab_confidence, tab_insight = st.tabs(["📊 대시보드", "🧾 리뷰 목록", "⚠️ 신뢰도 검증", "💡 핵심 인사이트"])

with tab_dashboard:
    c1, c2 = st.columns(2)
    sentiment_data = pd.DataFrame(
        [{"sentiment": k, "count": v} for k, v in stats.get("sentiment_distribution", {}).items()]
    )
    if not sentiment_data.empty:
        with c1:
            st.subheader("감성 비율")
            fig = px.pie(sentiment_data, names="sentiment", values="count", hole=0.35)
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            st.subheader("감성 절대 수치")
            fig = px.bar(sentiment_data, x="sentiment", y="count", text="count")
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("아직 분석 결과가 없습니다. 리뷰를 수집한 뒤 최신 리뷰 분석을 실행하세요.")

    topic_data = pd.DataFrame([{"topic": k, "count": v} for k, v in stats.get("topic_distribution", {}).items()])
    if not topic_data.empty:
        st.subheader("토픽 분포")
        fig = px.bar(topic_data, x="topic", y="count", text="count")
        st.plotly_chart(fig, use_container_width=True)

with tab_reviews:
    st.subheader("리뷰 및 분석 결과")
    if df.empty:
        st.info("표시할 리뷰가 없습니다. 먼저 Steam 리뷰를 수집하세요.")
    else:
        cols = [
            "review_id", "game_name", "steam_recommended", "sentiment", "confidence_pct",
            "confidence_badge", "topic", "keywords", "summary", "content",
        ]
        existing_cols = [c for c in cols if c in df.columns]
        st.dataframe(df[existing_cols], use_container_width=True, height=520)

with tab_confidence:
    st.subheader("신뢰도 분포와 위험 케이스")
    if validation_df.empty:
        st.info("분석 결과가 있어야 신뢰도 검증을 표시할 수 있습니다.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            fig = px.histogram(validation_df, x="confidence_pct", nbins=10, title="AI confidence 분포")
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            correct_series = validation_df["binary_correct"].dropna() if "binary_correct" in validation_df.columns else pd.Series(dtype=bool)
            accuracy = float(correct_series.mean() * 100) if len(correct_series) else 0
            avg_conf = float(validation_df["confidence_pct"].mean()) if "confidence_pct" in validation_df.columns else 0
            st.metric("Steam 추천 여부 기준 정확도", f"{accuracy:.1f}%")
            st.metric("평균 신뢰도", f"{avg_conf:.1f}%")
            st.caption("Steam recommended는 엄밀한 정답 라벨이 아니라, 사용자 추천 여부를 활용한 검증 기준입니다.")

        risk_df = validation_df[validation_df["high_confidence_wrong"] == True] if "high_confidence_wrong" in validation_df.columns else pd.DataFrame()
        st.markdown("### 고신뢰 오답 위험 케이스")
        if risk_df.empty:
            st.success("현재 기준에서는 신뢰도 85% 이상 오답 위험 케이스가 없습니다.")
        else:
            risk_cols = ["review_id", "steam_recommended", "steam_expected", "sentiment", "confidence_pct", "summary", "content"]
            st.dataframe(risk_df[[c for c in risk_cols if c in risk_df.columns]], use_container_width=True, height=360)

with tab_insight:
    st.subheader("핵심 인사이트: 신뢰도 ≠ 정확도")
    st.markdown(
        """
        AI가 높은 confidence를 출력하더라도 실제 정답을 보장하지는 않습니다.  
        이 앱은 Steam의 `recommended` 값을 임시 검증 기준으로 활용해, AI 감성 분석 결과와 사용자 추천 여부가 어긋나는 사례를 따로 보여줍니다.

        **실무 적용 기준**
        - 🟢 90% 이상: 자동 분류 후보이지만 샘플 검증 필요
        - 🟡 75~89%: 사람 검토 권장
        - 🔴 75% 미만: 반드시 사람 검토 필요
        - ⚠️ 85% 이상인데 Steam 추천 여부와 어긋나면 위험 케이스로 관리

        **왜 중요한가?**  
        리뷰 분석 결과를 마케팅, 업데이트 우선순위, QA 이슈 분류에 활용하려면 단순히 AI 결과를 믿는 것이 아니라, 
        원문 리뷰·추천 여부·confidence·오분류 패턴을 함께 확인해야 합니다.
        """
    )

st.divider()
st.caption("Steam Review Analyzer · Streamlit 단일 배포 가능 · FastAPI 백엔드는 main.py에서 선택적으로 실행")
