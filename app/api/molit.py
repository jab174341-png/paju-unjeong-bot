"""국토교통부 아파트매매 실거래가 API 클라이언트.

공공데이터포털 → "국토교통부_아파트매매 실거래가 자료" 서비스를 호출합니다.
"""

import os
import xml.etree.ElementTree as ET
from typing import List, Dict
from dotenv import load_dotenv
import requests

# .env 파일에서 환경변수 로드
load_dotenv()

API_KEY = os.getenv("MOLIT_API_KEY")
BASE_URL = (
    "https://apis.data.go.kr/1613000/"
    "RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade"
)


def fetch_apt_trades(
    lawd_cd: str,
    deal_ymd: str,
    num_rows: int = 1000,
) -> List[Dict[str, str]]:
    """한 시군구의 한 달치 아파트 매매 실거래 자료를 가져옵니다.

    Args:
        lawd_cd: 시군구 코드 (5자리). 예: 파주시 = "41480"
        deal_ymd: 계약년월 (YYYYMM, 6자리). 예: "202604"
        num_rows: 한 페이지에 가져올 건수 (기본 1000)

    Returns:
        거래 정보 dict의 리스트. 각 dict는 단지명/법정동/거래금액/전용면적/계약일 등 포함.

    Raises:
        ValueError: API 키가 .env에 설정되지 않은 경우.
        RuntimeError: API가 오류 코드를 반환한 경우.
        requests.HTTPError: HTTP 오류가 발생한 경우.
    """
    if not API_KEY or "여기에" in API_KEY:
        raise ValueError(
            ".env 파일에 MOLIT_API_KEY가 올바르게 설정되지 않았습니다."
        )

    params = {
        "serviceKey": API_KEY,
        "LAWD_CD": lawd_cd,
        "DEAL_YMD": deal_ymd,
        "numOfRows": num_rows,
        "pageNo": 1,
    }

    response = requests.get(BASE_URL, params=params, timeout=30)
    response.raise_for_status()

    return _parse_xml_response(response.text)


def _parse_xml_response(xml_text: str) -> List[Dict[str, str]]:
    """XML 응답을 파싱하여 거래 dict 리스트로 변환."""
    root = ET.fromstring(xml_text)

    # 결과 코드 확인 (정상 = "000")
    result_code = root.findtext(".//resultCode")
    if result_code and result_code != "000":
        result_msg = root.findtext(".//resultMsg") or "알 수 없는 오류"
        raise RuntimeError(f"API 오류 [{result_code}]: {result_msg}")

    items = root.findall(".//item")
    trades = []
    for item in items:
        trade = {}
        for child in item:
            # 태그명을 키로, 텍스트를 값으로 (None이면 빈 문자열)
            value = (child.text or "").strip()
            trade[child.tag] = value
        trades.append(trade)

    return trades
