"""FastAPI 메인 앱.

라우트:
- GET /                       : 단지 카드 목록 (홈)
- GET /complex/{apt_name}     : 단지 상세 (기간별 시세 + 차트)
                                 ?period=6M|3M|1M|1W

실행:
    uvicorn app.main:app --reload
"""

from pathlib import Path
from urllib.parse import unquote

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from app.analysis.loader import load_unjeong_trades
from app.analysis.aggregate import summarize_complex, get_trend_series
from app.chart.builder import build_trend_chart
from app.data.complexes import UNJEONG_COMPLEXES

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
    """홈: 30개 단지 카드 그리드. 각 카드에 최근 3개월 대표 평형 시세 표시."""
    df = load_unjeong_trades(months=12)

    cards = []
    for c in UNJEONG_COMPLEXES:
        summary = summarize_complex(df, c["name"], period="3M")
        if not summary:
            cards.append({**c, "main_bucket": None, "stats": None})
            continue
        # 거래 가장 많은 평형을 대표로
        main_bucket = max(summary.keys(), key=lambda b: summary[b]["count"])
        cards.append({**c, "main_bucket": main_bucket, "stats": summary[main_bucket]})

    return templates.TemplateResponse("index.html", {
        "request": request,
        "cards": cards,
    })


@app.get("/complex/{apt_name:path}", response_class=HTMLResponse)
def detail(request: Request, apt_name: str, period: str = "3M"):
    """단지 상세: 기간 선택 + 평형별 통계 + 차트 + 최근 거래."""
    apt_name = unquote(apt_name)
    df = load_unjeong_trades(months=12)

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

    return templates.TemplateResponse("detail.html", {
        "request": request,
        "apt_name": apt_name,
        "apt_info": apt_info,
        "period": period,
        "summary": summary,
        "charts": charts,
        "recent": recent,
    })
