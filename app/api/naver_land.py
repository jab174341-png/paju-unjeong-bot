"""네이버 부동산 (m.land.naver.com) 비공식 API 클라이언트.

cluster/ajax/complexList endpoint을 사용하여 시군구·법정동 단위로
단지 목록과 각 단지의 매물 요약(매물 수, 가격대, 면적 범위)을 가져옵니다.

⚠️ 비공식 API이므로 차단되거나 구조가 변경될 수 있습니다.
완화 전략:
- User-Agent 모바일로 위장
- 호출 간 1초 지연
- 결과를 SQLite 캐시에 3시간 보관
- 호출 실패 시 stale cache라도 반환
"""

import json
import time
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict
import requests

# 운정신도시 6개 법정동의 cortarNo (네이버 부동산 지역 코드)
UNJEONG_DONG_CORTAR = {
    "와동동": "4148012200",
    "야당동": "4148010800",
    "동패동": "4148011300",
    "목동동": "4148011700",
    "다율동": "4148010900",
    "교하동": "4148010700",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
        "Mobile/15E148 Safari/604.1"
    ),
    "Accept": "application/json",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://m.land.naver.com/",
}

DB_PATH = Path(__file__).resolve().parent.parent.parent / "cache.db"

# 회로 차단기 (Circuit Breaker):
# 네이버가 한 번이라도 timeout/실패하면 BACKOFF_SECONDS 동안 호출 자체를 건너뛰고
# 캐시(있으면 stale도 OK) 또는 빈 결과를 반환합니다.
# Render Singapore에서 네이버까지 느릴 때 매 동마다 timeout(15s × 6동 = 90초)을
# 기다리지 않도록 하기 위함.
_NAVER_BACKOFF_SECONDS = 600  # 10분
_naver_blocked_until = 0.0  # unix timestamp


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_schema():
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS naver_complex_list (
                cortar_no TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            )
        """)


def fetch_complex_list(cortar_no: str, max_age_hours: int = 3) -> List[Dict]:
    """한 법정동 안에 매매 매물이 있는 단지 목록을 반환.

    캐시된 데이터가 있고 max_age_hours 이내면 캐시 반환,
    아니면 네이버 호출 후 캐시에 저장.
    호출 실패 시 stale cache라도 반환 (있으면).
    """
    _ensure_schema()

    # 캐시 확인
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT payload, fetched_at FROM naver_complex_list WHERE cortar_no = ?",
            (cortar_no,),
        ).fetchone()

    if row:
        fetched_at = datetime.fromisoformat(row["fetched_at"])
        if datetime.now() - fetched_at < timedelta(hours=max_age_hours):
            return json.loads(row["payload"])

    # 회로 차단기: 최근 실패했다면 네이버 호출 자체를 건너뜀
    global _naver_blocked_until
    if time.time() < _naver_blocked_until:
        if row:
            return json.loads(row["payload"])  # stale 캐시라도 반환
        return []

    # 캐시 만료/없음 → 새로 호출
    url = (
        "https://m.land.naver.com/cluster/ajax/complexList"
        f"?cortarNo={cortar_no}&rletTpCd=APT&tradTpCd=A1&z=14"
    )
    try:
        r = requests.get(url, headers=HEADERS, timeout=5)  # 15s → 5s
        r.raise_for_status()
        data = r.json()
        result = data.get("result") or []
    except Exception as e:
        print(f"⚠️  네이버 API 호출 실패 (cortarNo={cortar_no}): {e}")
        # 회로 차단 활성화 (10분간 다른 cortarNo도 호출 안 함)
        _naver_blocked_until = time.time() + _NAVER_BACKOFF_SECONDS
        # 에러 시 stale cache라도 반환
        if row:
            return json.loads(row["payload"])
        return []

    # 캐시 저장
    with _get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO naver_complex_list "
            "(cortar_no, payload, fetched_at) VALUES (?, ?, ?)",
            (cortar_no, json.dumps(result, ensure_ascii=False),
             datetime.now().isoformat()),
        )
        conn.commit()

    return result


def fetch_all_unjeong_complexes(max_age_hours: int = 3) -> Dict[str, List[Dict]]:
    """운정 6개 동의 모든 단지 목록을 동별로 반환."""
    return {
        dong: fetch_complex_list(code, max_age_hours)
        for dong, code in UNJEONG_DONG_CORTAR.items()
    }
