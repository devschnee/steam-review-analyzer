"""Offline 30-sample validation for the Week6 confidence insight.

This script does not require Steam network access. It uses the local fallback/Groq
analyzer against a fixed 30-review validation set and stores results in SQLite.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from analyzer import analyze_review
from database import create_review, get_analysis, init_db, is_binary_correct, save_analysis

SAMPLE_PATH = Path("sample_data/week6_30_validation_samples.csv")
OUTPUT_PATH = Path("week6_validation_results.csv")
REPORT_PATH = Path("WEEK6_CONFIDENCE_REPORT.md")


def main() -> None:
    init_db()
    df = pd.read_csv(SAMPLE_PATH)
    results = []

    for idx, row in df.iterrows():
        review = create_review(
            app_id=str(row["game_id"]),
            game_id=str(row["game_id"]),
            game_name=str(row["game_name"]),
            source_review_id=f"week6_sample_{idx+1}",
            language="koreana",
            content=str(row["content"]),
            author="week6_sample",
            playtime_hours=0,
            recommended=bool(row["recommended"]),
            created_at=None,
        )
        existing = get_analysis(review["id"])
        if existing:
            analysis = existing
        else:
            analysis = save_analysis(review["id"], analyze_review(review["content"], game_name=review["game_name"]))

        correct = is_binary_correct(analysis["sentiment"], review["recommended"])
        results.append(
            {
                "sample_id": idx + 1,
                "game_id": row["game_id"],
                "game_name": row["game_name"],
                "category": row["category"],
                "content": row["content"],
                "steam_recommended": bool(row["recommended"]),
                "expected_sentiment_from_steam": "POSITIVE" if bool(row["recommended"]) else "NEGATIVE",
                "ai_sentiment": analysis["sentiment"],
                "confidence": analysis["confidence"],
                "topic": analysis["topic"],
                "summary": analysis["summary"],
                "source": analysis["source"],
                "is_binary_correct": correct,
                "is_high_confidence_wrong": bool((analysis["confidence"] >= 0.85) and (correct is False)),
            }
        )

    out = pd.DataFrame(results)
    out.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    accuracy = out["is_binary_correct"].mean() * 100
    avg_conf = out["confidence"].mean() * 100
    high_conf_wrong = int(out["is_high_confidence_wrong"].sum())
    by_category = out.groupby("category")["is_binary_correct"].mean().mul(100).round(1)

    category_table = "\n".join(["| 카테고리 | 정확도 |", "|---|---:|"] + [f"| {idx} | {val:.1f}% |" for idx, val in by_category.items()])

    report = f"""# Week6 신뢰도 검증 보고서

## 개요

Steam 리뷰 분석 앱의 핵심 인사이트인 **신뢰도 ≠ 정확도**를 확인하기 위해 30개 고정 샘플을 분석했습니다.

- 샘플 수: {len(out)}개
- 게임 수: {out['game_name'].nunique()}개
- 카테고리: {', '.join(out['category'].unique())}

## 결과

| 지표 | 값 |
|---|---:|
| 정확도 | {accuracy:.1f}% |
| 평균 신뢰도 | {avg_conf:.1f}% |
| 고신뢰 오답 수 | {high_conf_wrong}건 |

## 카테고리별 정확도

{category_table}

## 해석

AI의 confidence는 모델의 확신도일 뿐 실제 정확도와 동일하지 않습니다.  
따라서 앱에서는 85% 이상 고신뢰 결과라도 Steam 추천 여부와 어긋나는 경우를 **위험 케이스**로 별도 표시합니다.

## 적용 방안

- 90% 이상: 자동 분류 후보이지만 샘플 검증 유지
- 75~89%: 사람 검토 권장
- 75% 미만: 사람 검토 필수
- 85% 이상 오답: 프롬프트 개선 및 데이터 재검토 우선순위로 관리
"""
    REPORT_PATH.write_text(report, encoding="utf-8")

    print(f"Saved: {OUTPUT_PATH}")
    print(f"Saved: {REPORT_PATH}")
    print(f"Accuracy: {accuracy:.1f}%")
    print(f"Average confidence: {avg_conf:.1f}%")
    print(f"High-confidence wrong cases: {high_conf_wrong}")


if __name__ == "__main__":
    main()
