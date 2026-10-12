"""Basic API tests for the optional FastAPI backend."""

from __future__ import annotations

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def assert_status(name: str, response, expected: int) -> dict:
    ok = response.status_code == expected
    return {"case": name, "expected": expected, "actual": response.status_code, "status": "PASS" if ok else "FAIL"}


def main() -> None:
    results = []
    results.append(assert_status("GET /", client.get("/"), 200))
    results.append(assert_status("GET /reviews", client.get("/reviews?limit=5"), 200))
    created = client.post(
        "/reviews",
        json={
            "app_id": "268910",
            "game_name": "Cuphead",
            "content": "아트와 음악은 좋지만 난이도는 어렵습니다.",
            "recommended": True,
        },
    )
    results.append(assert_status("POST /reviews", created, 201))
    review_id = created.json().get("id")
    results.append(assert_status("GET /reviews/{id}", client.get(f"/reviews/{review_id}"), 200))
    results.append(assert_status("POST /analyze", client.post("/analyze", json={"review_id": review_id, "force_reanalyze": True}), 200))
    results.append(assert_status("GET /analysis/{id}", client.get(f"/analysis/{review_id}"), 200))
    results.append(assert_status("GET /stats", client.get("/stats"), 200))
    results.append(assert_status("GET missing review", client.get("/reviews/99999999"), 404))
    results.append(assert_status("POST invalid analyze", client.post("/analyze", json={"review_id": 99999999}), 404))

    passed = sum(1 for r in results if r["status"] == "PASS")
    print(f"ALL PASS: {passed}/{len(results)}" if passed == len(results) else f"PASS: {passed}/{len(results)}")
    for row in results:
        print(row)

    md = ["# API 테스트 결과", "", f"- 전체 케이스: {len(results)}", f"- PASS: {passed}", "", "| 케이스 | 기대 | 실제 | 결과 |", "|---|---:|---:|---|"]
    for row in results:
        md.append(f"| {row['case']} | {row['expected']} | {row['actual']} | {row['status']} |")
    with open("API_TEST_RESULTS.md", "w", encoding="utf-8") as f:
        f.write("\n".join(md))


if __name__ == "__main__":
    main()
