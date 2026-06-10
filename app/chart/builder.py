"""matplotlib으로 시세 추이 차트 PNG를 생성하여 static/charts/에 저장.

차트는 파일로 캐시되며, CHART_CACHE_SECONDS 이내에 같은 단지·평형이
다시 요청되면 재생성하지 않고 기존 파일 경로를 반환합니다 (matplotlib는 느려서).

⚠️ 스레드 안전성:
FastAPI는 동기 핸들러를 스레드풀에서 실행하고, 상세 페이지는 평형별
차트(84/59/100㎡)를 브라우저가 동시에 병렬 요청합니다. 전역 pyplot
상태(plt.gcf/plt.savefig/plt.close 등)는 스레드 안전하지 않아, 한 스레드의
savefig가 다른 스레드가 닫은 figure를 저장해 '백지 PNG'가 나오는 버그가
있었습니다. 그래서 이 모듈은 pyplot 전역 상태를 쓰지 않고
matplotlib.figure.Figure + FigureCanvasAgg 를 요청마다 독립적으로 생성합니다.
"""

import time
from pathlib import Path
from typing import Optional
import matplotlib

matplotlib.use("Agg")  # GUI 없는 서버 환경에서도 작동
import matplotlib.font_manager as fm
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
import pandas as pd

import os

# 한글 폰트 강제 설정 (Render 리눅스 컨테이너에 한글 폰트가 없을 때 대비).
# koreanize_matplotlib 패키지에 번들된 NanumGothic TTF 파일을 직접 잡아서
# FontProperties 로 모든 텍스트 요소에 명시 적용. rcParams 만 설정하면
# 일부 매니저 캐시 상황에서 적용이 안 됨.
KOREAN_FONT_PROP = None
try:
    import koreanize_matplotlib  # noqa: F401
    _pkg_dir = os.path.dirname(koreanize_matplotlib.__file__)
    for _candidate in (
        os.path.join(_pkg_dir, "fonts", "NanumGothic-Regular.ttf"),
        os.path.join(_pkg_dir, "NanumGothic-Regular.ttf"),
        os.path.join(_pkg_dir, "fonts", "NanumGothic.ttf"),
        os.path.join(_pkg_dir, "NanumGothic.ttf"),
    ):
        if os.path.exists(_candidate):
            fm.fontManager.addfont(_candidate)
            KOREAN_FONT_PROP = fm.FontProperties(fname=_candidate)
            break
except Exception as e:
    print(f"⚠️ 한글 폰트 설정 실패 (한글이 깨질 수 있음): {e}")

# 차트 PNG 파일 캐시 유효 기간 (초)
# 거래 데이터가 자주 바뀌지 않으므로 10분간 재사용해도 충분
CHART_CACHE_SECONDS = 10 * 60

CHART_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "charts"
CHART_DIR.mkdir(parents=True, exist_ok=True)


def safe_filename(name: str) -> str:
    """파일명으로 안전하게 변환 (한글은 그대로 두되 특수문자만 제거)."""
    return "".join(c if c.isalnum() else "_" for c in name)[:80]


def build_trend_chart(
    trend_df: pd.DataFrame,
    apt_name: str,
    area_bucket: str,
) -> Optional[str]:
    """월별 평균가 추이 차트를 PNG로 저장하고 웹 경로 반환.

    Args:
        trend_df: get_trend_series() 결과 (month, avg_amount, count)
        apt_name: 단지명
        area_bucket: 평형 ('59㎡대' 등)

    Returns:
        '/static/charts/...' 형식의 웹 경로. 데이터 없으면 None.
    """
    if trend_df.empty:
        return None

    filename = f"{safe_filename(apt_name)}__{safe_filename(area_bucket)}.png"
    filepath = CHART_DIR / filename

    # 파일이 이미 있고 신선하면 재생성 스킵 (matplotlib가 느림)
    if filepath.exists():
        age = time.time() - filepath.stat().st_mtime
        if age < CHART_CACHE_SECONDS:
            return f"/static/charts/{filename}"

    # pyplot 전역 상태를 쓰지 않고 Figure 를 직접 생성 (스레드 안전).
    fig = Figure(figsize=(10, 4.2), dpi=110)
    FigureCanvasAgg(fig)  # Agg 캔버스 연결 (savefig 보장)
    ax = fig.subplots()

    # 마이너스 기호 깨짐 방지 (한글 폰트와 충돌하기 쉬움)
    ax.ticklabel_format(useOffset=False, axis="y")
    fig.patch.set_facecolor("white")

    months = trend_df["month"].tolist()
    amounts_eok = [a / 10000 for a in trend_df["avg_amount"].tolist()]

    ax.plot(
        months, amounts_eok,
        marker="o", linewidth=2.5, color="#3b82f6",
        markersize=7, markerfacecolor="white",
        markeredgewidth=2, markeredgecolor="#3b82f6",
    )

    # 데이터 포인트 위에 값 표시 (ASCII 숫자라서 폰트 영향 없음)
    for i, v in enumerate(amounts_eok):
        ax.annotate(
            f"{v:.1f}", (i, v),
            textcoords="offset points", xytext=(0, 10),
            ha="center", fontsize=9, color="#1e3a8a",
        )

    # 한글 텍스트는 fontproperties 명시적으로 적용
    title_kwargs = {"fontsize": 13, "pad": 15}
    ylabel_kwargs = {"fontsize": 11}
    if KOREAN_FONT_PROP is not None:
        title_kwargs["fontproperties"] = KOREAN_FONT_PROP
        ylabel_kwargs["fontproperties"] = KOREAN_FONT_PROP
    ax.set_title(f"{apt_name} {area_bucket} 월별 평균가", **title_kwargs)
    ax.set_ylabel("평균 거래가 (억원)", **ylabel_kwargs)

    # x/y축 라벨 한글 폰트 적용 (혹시 모를 한글 들어갈 때 대비)
    if KOREAN_FONT_PROP is not None:
        for lbl in ax.get_xticklabels() + ax.get_yticklabels():
            lbl.set_fontproperties(KOREAN_FONT_PROP)
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # y축 여유
    if amounts_eok:
        margin = (max(amounts_eok) - min(amounts_eok)) * 0.2 or 0.5
        ax.set_ylim(min(amounts_eok) - margin, max(amounts_eok) + margin * 1.5)

    # x축 라벨 회전 (pyplot 대신 OO API 사용)
    for lbl in ax.get_xticklabels():
        lbl.set_rotation(45)
        lbl.set_horizontalalignment("right")

    fig.tight_layout()
    fig.savefig(filepath, bbox_inches="tight", facecolor="white")
    # Figure 는 pyplot 에 등록되지 않으므로 close 불필요 (GC 가 회수).

    return f"/static/charts/{filename}"
