"""matplotlib으로 시세 추이 차트 PNG를 생성하여 static/charts/에 저장."""

from pathlib import Path
from typing import Optional
import matplotlib

matplotlib.use("Agg")  # GUI 없는 서버 환경에서도 작동
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import pandas as pd

CHART_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "charts"
CHART_DIR.mkdir(parents=True, exist_ok=True)


def _setup_korean_font():
    """한글 폰트를 자동 감지하여 설정. Mac/Linux/Windows 모두 시도."""
    candidates = [
        "AppleGothic",          # macOS 기본
        "Apple SD Gothic Neo",  # macOS 모던
        "NanumGothic",          # 리눅스/공통
        "Malgun Gothic",        # Windows
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    for c in candidates:
        if c in available:
            plt.rcParams["font.family"] = c
            break
    plt.rcParams["axes.unicode_minus"] = False  # 마이너스 기호 깨짐 방지


_setup_korean_font()


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

    fig, ax = plt.subplots(figsize=(10, 4.2), dpi=110)

    months = trend_df["month"].tolist()
    amounts_eok = [a / 10000 for a in trend_df["avg_amount"].tolist()]

    ax.plot(
        months, amounts_eok,
        marker="o", linewidth=2.5, color="#3b82f6",
        markersize=7, markerfacecolor="white",
        markeredgewidth=2, markeredgecolor="#3b82f6",
    )

    # 데이터 포인트 위에 값 표시
    for i, v in enumerate(amounts_eok):
        ax.annotate(
            f"{v:.1f}", (i, v),
            textcoords="offset points", xytext=(0, 10),
            ha="center", fontsize=9, color="#1e3a8a",
        )

    ax.set_title(f"{apt_name}  {area_bucket}  월별 평균가", fontsize=13, pad=15)
    ax.set_ylabel("평균 거래가 (억원)", fontsize=11)
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # y축 여유
    if amounts_eok:
        margin = (max(amounts_eok) - min(amounts_eok)) * 0.2 or 0.5
        ax.set_ylim(min(amounts_eok) - margin, max(amounts_eok) + margin * 1.5)

    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(filepath, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    return f"/static/charts/{filename}"
