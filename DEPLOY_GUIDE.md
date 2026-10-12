# Streamlit Cloud 배포 가이드

## 1. GitHub 저장소 만들기

1. GitHub에서 새 Repository를 생성합니다.
2. 이 프로젝트 폴더의 파일을 업로드합니다.
3. 실제 `.env` 파일과 `.streamlit/secrets.toml`은 업로드하지 않습니다.

업로드해야 하는 주요 파일:

```text
app.py
steam_client.py
analyzer.py
database.py
requirements.txt
.streamlit/config.toml
sample_data/week6_30_validation_samples.csv
README.md
```

## 2. Streamlit Community Cloud에서 배포

1. Streamlit Community Cloud 접속
2. New app 선택
3. GitHub 저장소 선택
4. Main file path에 `app.py` 입력
5. Deploy 클릭

## 3. Secrets 설정

앱 설정의 Secrets에 아래 형식으로 입력합니다.

```toml
GROQ_API_KEY = "gsk_xxxxxxxxxxxxxxxxx"
GROQ_MODEL = "llama-3.1-8b-instant"
DB_PATH = "steam_review_analyzer.db"
```

GROQ_API_KEY를 넣지 않아도 앱은 fallback 분석으로 실행됩니다.

## 4. 배포 후 확인

앱 주소에 접속한 뒤 다음 순서로 테스트합니다.

1. Steam App ID 입력: `553850`
2. 리뷰 언어: `koreana`
3. 수집할 리뷰 수: `100`
4. `① Steam 리뷰 수집` 클릭
5. 수집 리뷰가 20개 이상인지 확인
6. `② 최신 리뷰 분석` 클릭
7. 통계 카드, 차트, 리뷰 목록, 신뢰도 검증 탭 확인

## 5. 공개 앱 운영 시 주의점

- 분석 개수를 너무 크게 열어두면 API 비용이 증가할 수 있습니다.
- 무료 배포 환경의 SQLite는 장기 저장소로 적합하지 않습니다.
- 실사용 서비스로 확장하려면 Supabase, PostgreSQL, Neon 등 외부 DB를 권장합니다.
- 사용자 입력 App ID에 대한 예외 처리를 유지해야 합니다.
