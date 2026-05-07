"""SQLite 기반 거래 데이터 캐시.

매번 국토부 API를 호출하지 않고, 한 번 받은 월별 데이터는 로컬 SQLite에 저장합니다.
- 동일 월 재요청 시 캐시에서 즉시 반환
- '오늘 기준 최근 월'은 신규 거래가 추가되므로 1일 단위로 갱신
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

# DB 파일은 프로젝트 루트의 cache.db에 저장
DB_PATH = Path(__file__).resolve().parent.parent.parent / "cache.db"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_schema():
    """필요한 테이블이 없으면 생성."""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                lawd_cd TEXT NOT NULL,
                deal_ymd TEXT NOT NULL,
                payload TEXT NOT NULL,  -- JSON list of trade dicts
                fetched_at TEXT NOT NULL,
                PRIMARY KEY (lawd_cd, deal_ymd)
            )
        """)


def get_cached(lawd_cd: str, deal_ymd: str, max_age_hours: int = 24) -> Optional[List[Dict]]:
    """캐시된 데이터를 반환. 없거나 만료되었으면 None."""
    _ensure_schema()
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT payload, fetched_at FROM trades WHERE lawd_cd=? AND deal_ymd=?",
            (lawd_cd, deal_ymd),
        ).fetchone()
    if not row:
        return None

    fetched_at = datetime.fromisoformat(row["fetched_at"])
    if datetime.now() - fetched_at > timedelta(hours=max_age_hours):
        return None  # 만료됨

    import json
    return json.loads(row["payload"])


def save_to_cache(lawd_cd: str, deal_ymd: str, trades: List[Dict]):
    """API에서 받은 데이터를 캐시에 저장 (덮어쓰기)."""
    _ensure_schema()
    import json
    payload = json.dumps(trades, ensure_ascii=False)
    with _get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO trades (lawd_cd, deal_ymd, payload, fetched_at) VALUES (?, ?, ?, ?)",
            (lawd_cd, deal_ymd, payload, datetime.now().isoformat()),
        )
        conn.commit()
