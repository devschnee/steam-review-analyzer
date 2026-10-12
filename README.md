# Steam Review Analyzer Web App

> **GitHub 공개판 실행 안내:** API 키를 등록하지 않으면 감성 분석은 **규칙 기반(fallback)** 으로 동작합니다. LLM 분석을 지원하는 코드가 포함돼 있으나, 공개판에 LLM API 키는 들어 있지 않습니다.
> **검증 수치의 출처:** 동봉된 `week6_validation_results.csv`는 **30건 모두 규칙 기반 분석 결과**입니다. 추천 여부와 이진 감성 판정을 비교할 수 있는 20건 중 18건이 일치(90%)했습니다. 따라서 이 수치를 LLM 성능이나 30건 전체의 정확도로 소개하지 않습니다.

Steam App ID 또는 Steam 상점 URL을 입력하면 공개 Steam 리뷰를 수집하고, 최신 리뷰 일부를 LLM 또는 fallback 규칙으로 분석한 뒤 Streamlit 대시보드로 보여주는 웹앱입니다.

기존 Week5/Week6 Cuphead 프로젝트의 DB/API/UI 구조를 유지하되, Cuphead 고정 분석에서 벗어나 **어떤 Steam 게임이든 App ID 기반으로 분석할 수 있도록 리팩토링**했습니다.

---

## 1. 핵심 기능

1. **Steam App ID/URL 입력 기반 리뷰 수집**
   - 예: `268910`, `553850`, `https://store.steampowered.com/app/553850`
   - Steam 공개 리뷰 API에서 리뷰를 수집합니다.
   - 기본 언어는 한국어(`koreana`)입니다.

2. **수집과 분석 분리**
   - 리뷰는 최대 200개까지 수집할 수 있습니다.
   - 실제 AI 분석은 최신 10~50개 범위에서 선택합니다.
   - 최소 리뷰 수 기준보다 적으면 경고를 표시합니다.

3. **SQLite 저장**
   - `reviews` 테이블: 원본 Steam 리뷰 저장
   - `analysis_results` 테이블: AI/fallback 분석 결과 저장
   - `FOREIGN KEY`, `UNIQUE(app_id, source_review_id)`, `CHECK`, 인덱스 적용

4. **Streamlit 대시보드**
   - 통계 카드 4개
   - 감성 비율 원형 차트
   - 감성 절대 수치 막대 차트
   - 토픽 분포 차트
   - 리뷰 목록/필터
   - 신뢰도 배지
   - 고신뢰 오답 위험 케이스 테이블

5. **신뢰도 ≠ 정확도 인사이트**
   - Steam `recommended` 값을 임시 검증 기준으로 활용합니다.
   - AI confidence가 높아도 Steam 추천 여부와 어긋나면 위험 케이스로 분리합니다.

6. **배포 가능 구조**
   - `app.py` 하나로 Streamlit Community Cloud 배포 가능
   - `main.py`는 선택적 FastAPI 백엔드로 유지

---

## 2. 파일 구조

```text
steam_review_analyzer_webapp/
├─ app.py                         # Streamlit 배포용 단일 웹앱
├─ main.py                        # 선택적 FastAPI 백엔드
├─ steam_client.py                # Steam 공개 리뷰 수집
├─ analyzer.py                    # Groq/fallback 리뷰 분석
├─ database.py                    # SQLite DB 계층
├─ models.py                      # FastAPI Pydantic 모델
├─ run_week6_sample_validation.py # 30개 샘플 검증
├─ test_api.py                    # FastAPI 9개 케이스 테스트
├─ requirements.txt
├─ .env.example
├─ .gitignore
├─ run_webapp.bat                 # Windows 더블클릭 실행용, 브라우저 1회 자동 열기 포함
├─ run_api.bat
├─ run_validation.bat
├─ API_TEST_RESULTS.md
├─ WEEK6_CONFIDENCE_REPORT.md
├─ week6_validation_results.csv
├─ submission_note.md
├─ DEPLOY_GUIDE.md
├─ .streamlit/
│  ├─ config.toml
│  └─ secrets.toml.example
└─ sample_data/
   └─ week6_30_validation_samples.csv
```

---

## 3. 로컬 실행 방법

### 방법 A. 더블클릭 실행

Windows에서 압축을 풀고 아래 파일을 더블클릭합니다.

```text
run_webapp.bat
```

실행 후 기본 브라우저에서 `http://localhost:8501`이 자동으로 열립니다. 자동으로 열리지 않으면 터미널에 표시된 주소를 직접 입력하면 됩니다.

자동으로 가상환경 생성, 패키지 설치, Streamlit 실행을 시도합니다.

### 방법 B. PowerShell 수동 실행

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

브라우저 접속 주소:

```text
http://localhost:8501
```

---

## 4. FastAPI 백엔드 실행

Streamlit 단일 앱만 사용해도 되지만, API 구조를 확인하려면 다음을 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

Swagger UI:

```text
http://localhost:8000/docs
```

---

## 5. 환경변수

`.env.example`을 복사해 `.env`를 만듭니다.

```env
GROQ_API_KEY=여기에_개인_Groq_API_Key
GROQ_MODEL=llama-3.1-8b-instant
DB_PATH=steam_review_analyzer.db
```

API 키가 없으면 fallback 규칙 기반 분석으로 동작합니다.  
실제 `.env` 파일은 GitHub 또는 제출 ZIP에 포함하지 않습니다.

---

## 6. Streamlit Cloud 배포

이 프로젝트는 `app.py`를 메인 파일로 지정하면 Streamlit Community Cloud에 배포할 수 있습니다.

배포 시 필요한 설정:

```text
Main file path: app.py
Requirements file: requirements.txt
```

Secrets 예시:

```toml
GROQ_API_KEY = "gsk_xxxxxxxxxxxxxxxxx"
GROQ_MODEL = "llama-3.1-8b-instant"
DB_PATH = "steam_review_analyzer.db"
```

자세한 절차는 `DEPLOY_GUIDE.md`를 확인하세요.

---

## 7. 30개 샘플 검증

Week6 기준의 30개 샘플 검증은 다음 명령으로 실행합니다.

```powershell
.\.venv\Scripts\python.exe run_week6_sample_validation.py
```

생성 결과:

```text
week6_validation_results.csv
WEEK6_CONFIDENCE_REPORT.md
```

현재 검증 결과 요약:

```text
샘플 수: 30개
Steam 추천 여부 기준 일치율: 90.0% (판정 가능한 20건 중 18건, 30건 전체 fallback)
평균 신뢰도: 75.8%
고신뢰 오답 수: 0건
```

---

## 8. API 테스트

```powershell
.\.venv\Scripts\python.exe test_api.py
```

현재 결과:

```text
ALL PASS: 9/9
```

---

## 9. 한계점

- Steam `recommended`는 사람이 직접 붙인 감성 정답 라벨이 아니라 추천/비추천 기준입니다.
- NEUTRAL/MIXED는 binary 추천 여부와 직접 비교하기 어려워 ambiguous로 처리합니다.
- 무료 LLM API는 속도와 호출량 제한이 있으므로 분석 개수를 제한했습니다.
- Streamlit Community Cloud의 SQLite 파일은 영구 DB 서비스가 아니므로 장기 운영 시 외부 DB 전환이 필요합니다.
- 공개 앱에서 API 키 비용을 보호하려면 분석 개수 제한, 캐싱, 사용자별 쿼터가 필요합니다.

---

## 10. 프로젝트 요약

Week5에서 만든 DB/API 구조와 Week6 UI 요구사항을 기반으로, Cuphead 고정 분석기를 범용 Steam 리뷰 분석 웹앱으로 확장했습니다.  
사용자는 Steam App ID만 입력하면 리뷰 수집, 분석, 시각화, 신뢰도 검증까지 하나의 화면에서 확인할 수 있습니다.


## 수집 안정성 보완

Steam 공개 리뷰에는 빈 리뷰, 1글자 반응, 중복 recommendation id가 포함될 수 있습니다. 웹앱은 이러한 행을 자동으로 건너뛰고 나머지 리뷰 저장을 계속 진행하도록 구성했습니다. 따라서 일부 이상치 리뷰 때문에 전체 수집 과정이 중단되지 않습니다.
