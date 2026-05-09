"""FastAPI 메인 앱.

라우트:
- GET /                       : 단지 카드 목록 (홈)
- GET /complex/{apt_name}     : 단지 상세 (기간별 시세 + 차트)
                                 ?period=6M|3M|1M|1W

실행:
    uvicorn app.main:app --reload
"""

from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import unquote

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse

from app.analysis.loader import load_unjeong_trades
from app.analysis.aggregate import summarize_complex, get_trend_series
from app.analysis.listings import get_listings_summary
from app.chart.builder import build_trend_chart
from app.data.complexes import UNJEONG_COMPLEXES

# ─── 메모리 캐시 (서버 재시작 시 초기화) ───────────────────
# Render 무료 플랜은 CPU 0.1, RAM 512MB로 빠듯해서, 매 요청마다
# 12개월 거래 데이터를 다시 분석하면 1~2초 걸립니다.
# 결과를 짧게 메모리에 캐시해서 반복 요청을 즉시 처리합니다.
_trades_cache = {"df": None, "expires_at": None}
_home_cards_cache = {"cards": None, "expires_at": None}
TRADES_TTL = timedelta(minutes=30)
HOME_CARDS_TTL = timedelta(minutes=10)


def _get_trades_cached():
    """12개월치 운정 거래 DataFrame을 30분 캐시로 반환."""
    now = datetime.now()
    if (
        _trades_cache["df"] is not None
        and _trades_cache["expires_at"]
        and now < _trades_cache["expires_at"]
    ):
        return _trades_cache["df"]
    df = load_unjeong_trades(months=12)
    _trades_cache["df"] = df
    _trades_cache["expires_at"] = now + TRADES_TTL
    return df


def _build_home_cards():
    """모든 단지의 카드 데이터(3개월 대표 평형) 계산."""
    df = _get_trades_cached()
    cards = []
    for c in UNJEONG_COMPLEXES:
        summary = summarize_complex(df, c["name"], period="3M")
        if not summary:
            cards.append({**c, "main_bucket": None, "stats": None})
            continue
        main_bucket = max(summary.keys(), key=lambda b: summary[b]["count"])
        cards.append({**c, "main_bucket": main_bucket, "stats": summary[main_bucket]})
    return cards


def _get_home_cards_cached():
    """홈 카드 결과를 10분 캐시로 반환."""
    now = datetime.now()
    if (
        _home_cards_cache["cards"] is not None
        and _home_cards_cache["expires_at"]
        and now < _home_cards_cache["expires_at"]
    ):
        return _home_cards_cache["cards"]
    cards = _build_home_cards()
    _home_cards_cache["cards"] = cards
    _home_cards_cache["expires_at"] = now + HOME_CARDS_TTL
    return cards

PROJECT_ROOT = Path(__file__).resolve().parent.parent

app = FastAPI(title="파주 운정 시세 대시보드")
app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "static"), name="static")
templates = Jinja2Templates(directory=PROJECT_ROOT / "templates")


def fmt_won(manwon):
    """85275(만원) → '8억 5,275만원'."""
    if manwon is None:
        return "—"
    manwon = int(manwon)
    eok = manwon // 10000
    rest = manwon % 10000
    if eok and rest:
        return f"{eok}억 {rest:,}만원"
    if eok:
        return f"{eok}억"
    return f"{rest:,}만원"


templates.env.filters["won"] = fmt_won


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    """홈: 단지 카드 그리드. 각 카드에 최근 3개월 대표 평형 시세 표시.

    카드 데이터는 메모리에 10분간 캐시되어 반복 요청에 즉시 응답.
    """
    cards = _get_home_cards_cached()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "cards": cards,
    })


@app.get("/complex/{apt_name:path}", response_class=HTMLResponse)
def detail(request: Request, apt_name: str, period: str = "3M"):
    """단지 상세: 기간 선택 + 평형별 통계 + 차트 + 최근 거래."""
    apt_name = unquote(apt_name)
    df = _get_trades_cached()

    summary = summarize_complex(df, apt_name, period=period)

    # 평형별 차트 생성
    charts = {}
    for bucket in summary.keys():
        trend = get_trend_series(df, apt_name, bucket, months=12)
        charts[bucket] = build_trend_chart(trend, apt_name, bucket)

    # 최근 거래 10건
    recent_df = (
        df[df["apt_name"] == apt_name]
        .sort_values("deal_date", ascending=False)
        .head(10)
    )
    recent = recent_df.to_dict(orient="records")

    apt_info = next((c for c in UNJEONG_COMPLEXES if c["name"] == apt_name), None)

    # 네이버 매물 정보는 비동기로 별도 호출 (/api/listings)
    # 페이지 렌더 시 네이버를 기다리지 않아 빠른 응답 보장
    return templates.TemplateResponse("detail.html", {
        "request": request,
        "apt_name": apt_name,
        "apt_info": apt_info,
        "period": period,
        "summary": summary,
        "charts": charts,
        "recent": recent,
    })


@app.get("/api/listings")
def api_listings(apt_name: str, dong: str):
    """네이버 부동산 매물 요약 (JSON, 비동기 로드용).

    실패하면 {"available": False} 반환하여 프론트가 섹션을 숨김.
    """
    try:
        result = get_listings_summary(apt_name, dong)
        if result:
            return JSONResponse({"available": True, **result})
    except Exception as e:
        print(f"⚠️  /api/listings 실패 ({apt_name}): {e}")
    return JSONResponse({"available": False})
