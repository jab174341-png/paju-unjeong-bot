"""FastAPI 메인 앱.

라우트:
- GET /                       : 단지 카드 목록 (홈)
- GET /complex/{apt_name}     : 단지 상세 (기간별 시세 + 차트)
                                 ?period=6M|3M|1M|1W

실행:
    uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import unquote, quote

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse

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
# UptimeRobot이 5분마다 핑을 쳐서 서버를 깨워두므로, 메모리 캐시가
# 자주 비워지지 않습니다. TTL을 길게 잡아 캐시 미스 페널티를 최소화.
# (실제 데이터 갱신은 SQLite 캐시 레이어에서 별도로 일어남)
TRADES_TTL = timedelta(hours=4)
HOME_CARDS_TTL = timedelta(hours=1)


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """서버 시작 시:
    1) 차트 캐시 디렉토리를 비워서 stale 차트 제거 (이전 배포에서 깨진 차트 방지)
    2) 거래 데이터 + 홈 카드 캐시 워밍해서 첫 사용자 요청이 즉시 응답되게 함
    """
    # 1) 차트 디렉토리 정리
    try:
        chart_dir = PROJECT_ROOT / "static" / "charts"
        if chart_dir.exists():
            removed = 0
            for f in chart_dir.glob("*.png"):
                try:
                    f.unlink()
                    removed += 1
                except Exception:
                    pass
            print(f"🧹 차트 캐시 정리: {removed}개 PNG 삭제")
    except Exception as e:
        print(f"⚠️  차트 캐시 정리 실패: {e}")

    # 2) 데이터 캐시 워밍
    try:
        print("🔥 서버 시작: 캐시 워밍 중...")
        cards = _get_home_cards_cached()
        print(f"✅ 캐시 워밍 완료 ({len(cards)}개 단지)")
    except Exception as e:
        print(f"⚠️  캐시 워밍 실패 (서버는 정상 작동): {e}")
    yield


app = FastAPI(title="파주 운정 시세 대시보드", lifespan=lifespan)
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

    # 차트는 /chart endpoint 에서 비동기로 생성됨 (페이지 즉시 응답 보장).
    # URL에 cache-bust 파라미터(파일 mtime)를 포함시켜 차트가 재생성될 때마다
    # URL 자체가 바뀌게 함 → 브라우저가 옛 PNG를 캐시해서 보여주는 문제 방지.
    chart_dir = PROJECT_ROOT / "static" / "charts"
    charts = {}
    for bucket in summary.keys():
        # safe_filename 과 동일한 변환 로직
        safe_apt = "".join(c if c.isalnum() else "_" for c in apt_name)[:80]
        safe_bkt = "".join(c if c.isalnum() else "_" for c in bucket)[:80]
        chart_file = chart_dir / f"{safe_apt}__{safe_bkt}.png"
        v = int(chart_file.stat().st_mtime) if chart_file.exists() else 0
        charts[bucket] = (
            f"/chart?apt_name={quote(apt_name)}&bucket={quote(bucket)}&v={v}"
        )

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


@app.get("/chart")
def chart_endpoint(apt_name: str, bucket: str, v: int = 0):
    """차트 PNG를 즉석 생성하여 서빙. 페이지 렌더와 분리되어 병렬 로드.

    matplotlib 차트 생성은 약 1초/장이 걸리므로, 페이지 렌더 핸들러에서
    분리해야 페이지를 즉시 응답할 수 있음. 브라우저는 <img> 태그로 이
    엔드포인트를 호출하고, 동시에 다른 차트도 병렬로 가져옴.

    v 파라미터는 cache-bust 용도로만 사용 (실제 처리에는 영향 없음).
    detail 핸들러에서 차트 파일의 mtime을 v=...에 넣어주면 차트가
    재생성될 때마다 URL이 달라져 브라우저가 자동으로 새 PNG를 받음.
    """
    try:
        df = _get_trades_cached()
        trend = get_trend_series(df, apt_name, bucket, months=12)
        if trend.empty:
            raise HTTPException(status_code=404, detail="no trend data")

        path = build_trend_chart(trend, apt_name, bucket)
        if not path:
            raise HTTPException(status_code=404, detail="chart build failed")

        # path: '/static/charts/foo.png'
        file_path = PROJECT_ROOT / path.lstrip("/")
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="chart file missing")

        # 브라우저가 캐시할 수 있게 Cache-Control 설정 (10분)
        return FileResponse(
            file_path,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=600"},
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"⚠️  Chart endpoint error ({apt_name}/{bucket}): {e}")
        raise HTTPException(status_code=500, detail="chart generation failed")


@app.get("/api/debug/data")
def debug_data():
    """현재 in-memory 캐시 상태 진단용. 단지별 거래 수 반환."""
    df = _get_trades_cached()
    if df is None or df.empty:
        return JSONResponse({"total_trades": 0, "unique_complexes": 0})
    counts = df["apt_name"].value_counts().to_dict()
    return JSONResponse({
        "total_trades": int(len(df)),
        "unique_complexes": int(df["apt_name"].nunique()),
        "complex_trade_counts": {k: int(v) for k, v in counts.items()},
    })


@app.get("/api/debug/refresh")
def debug_refresh():
    """메모리 캐시 강제 무효화. 다음 요청 때 재빌드됨."""
    _trades_cache["df"] = None
    _trades_cache["expires_at"] = None
    _home_cards_cache["cards"] = None
    _home_cards_cache["expires_at"] = None
    # 차트 PNG 캐시도 청소
    chart_dir = PROJECT_ROOT / "static" / "charts"
    removed = 0
    if chart_dir.exists():
        for f in chart_dir.glob("*.png"):
            try:
                f.unlink()
                removed += 1
            except Exception:
                pass
    return JSONResponse({"ok": True, "charts_removed": removed})


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
