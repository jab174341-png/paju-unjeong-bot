# 파주 운정 시세 대시보드

국토교통부 실거래가 데이터로 파주 운정신도시 31개 주요 단지의
시세 변화(6개월/3개월/1개월/주간)를 보여주는 웹 대시보드.

## 기술 스택
- Python 3.11 + FastAPI
- pandas (데이터 분석)
- matplotlib (차트 생성)
- Jinja2 (HTML 템플릿)
- SQLite (API 응답 캐시)

## 로컬 실행

```bash
# 1. 가상환경 생성·활성화
python3 -m venv venv
source venv/bin/activate

# 2. 라이브러리 설치
pip install -r requirements.txt

# 3. 환경변수 설정
cp .env.example .env
# .env 파일을 열어 MOLIT_API_KEY 값을 본인 키로 교체

# 4. 서버 실행
uvicorn app.main:app --reload

# 5. 브라우저에서 http://127.0.0.1:8000 접속
```

## 환경변수
- `MOLIT_API_KEY`: 공공데이터포털 "국토교통부_아파트매매 실거래가 자료" Decoding 키
  - 발급: https://www.data.go.kr

## 배포 (Cloudtype)
- Python 자동 감지 + Procfile 사용
- 환경변수 `MOLIT_API_KEY` 등록 필요
- 시작 명령: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

## 데이터 출처
국토교통부 실거래가 공개시스템 (신고지연 약 30일, 최근 데이터는 잠정치)
