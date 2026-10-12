# API 테스트 결과

- 전체 케이스: 9
- PASS: 9

| 케이스 | 기대 | 실제 | 결과 |
|---|---:|---:|---|
| GET / | 200 | 200 | PASS |
| GET /reviews | 200 | 200 | PASS |
| POST /reviews | 201 | 201 | PASS |
| GET /reviews/{id} | 200 | 200 | PASS |
| POST /analyze | 200 | 200 | PASS |
| GET /analysis/{id} | 200 | 200 | PASS |
| GET /stats | 200 | 200 | PASS |
| GET missing review | 404 | 404 | PASS |
| POST invalid analyze | 404 | 404 | PASS |