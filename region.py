# region.py — JSON 전용 CLI (HTTPS→HTTP 폴백, 전국 스캔 옵션, 표준 라이브러리만)
from __future__ import annotations
import argparse, json, os, re, sys, time
import urllib.parse as up, urllib.request as ur
from typing import Any, Iterable, List, Tuple

HTTP_URL  = "http://apis.data.go.kr/1741000/StanReginCd/getStanReginCdList"
HTTPS_URL = "https://apis.data.go.kr/1741000/StanReginCd/getStanReginCdList"

PROVINCES = [
    "서울특별시","부산광역시","대구광역시","인천광역시","광주광역시","대전광역시","울산광역시",
    "세종특별자치시","경기도","강원특별자치도","강원도","충청북도","충청남도",
    "전북특별자치도","전라북도","전라남도","경상북도","경상남도","제주특별자치도"
]

# ------------------------ 공공데이터 호출 ------------------------

def _service_key(cli_key: str|None) -> str:
    key = (cli_key or os.getenv("PUBLICDATA_KEY") or "").strip()
    if not key:
        print("ERROR: serviceKey 필요 — --key 또는 PUBLICDATA_KEY", file=sys.stderr)
        raise SystemExit(3)
    return key if "%" in key else up.quote(key, safe="")

def _http_get(url: str, timeout: int) -> bytes:
    req = ur.Request(url, headers={"User-Agent": "region-cd/stdlib-json/1.3"})
    with ur.urlopen(req, timeout=timeout) as r:
        return r.read()

def _rows_from_json(data: Any) -> Tuple[List[dict], dict]:
    rows: List[dict] = []; head: dict = {}
    if isinstance(data, dict):
        blocks = data.get("StanReginCd")
        if isinstance(blocks, list):
            for b in blocks:
                if isinstance(b, dict):
                    if isinstance(b.get("row"), list):
                        rows.extend([x for x in b["row"] if isinstance(x, dict)])
                    if isinstance(b.get("head"), list) and b["head"]:
                        if isinstance(b["head"][0], dict):
                            head = b["head"][0]
    return rows, head

def _build_qs(key: str, q: str, page: int, rows: int) -> str:
    return (
        f"serviceKey={key}&pageNo={page}&numOfRows={rows}"
        f"&type=JSON&locatadd_nm={up.quote(q)}"
    )

def _fetch_json_with_fallback(key: str, q: str, page: int, rows: int, timeout: int,
                              tries: int = 2):
    last_err = None
    for attempt in range(tries):
        for base, scheme in ((HTTPS_URL, "https"), (HTTP_URL, "http")):
            url = f"{base}?{_build_qs(key, q, page, rows)}"
            try:
                raw = _http_get(url, timeout)
                try:
                    data = json.loads(raw.decode("utf-8"))
                except Exception:
                    data = json.loads(raw)
                return _rows_from_json(data), scheme
            except Exception as e:
                last_err = e
        time.sleep(0.4 * (attempt + 1))
    if last_err:
        raise last_err
    return ([], {}), "unknown"

def _filter_codes(rows: List[dict], query: str) -> List[str]:
    tokens = [t for t in re.split(r"\s+", query.strip()) if t]
    out: List[str] = []
    for r in rows:
        hay = f"{r.get('locatadd_nm','')} {r.get('locallow_nm','')}"
        if all(t in hay for t in tokens):
            rc = r.get("region_cd")
            if rc:
                out.append(str(rc))
    return sorted(set(out))

def fetch_region_cd(key: str, q: str, page: int, rows: int,
                    timeout: int, scan_all: bool, debug: bool):
    dbg: dict = {"query": q}
    try:
        (rows_json, head), scheme = _fetch_json_with_fallback(key, q, page, rows, timeout)
        dbg.update({"phase": "direct", "scheme": scheme, **head})
        if rows_json:
            codes = _filter_codes(rows_json, q)
            if codes:
                return codes, dbg
    except Exception as e:
        dbg.update({"direct_error": repr(e)})
    if scan_all:
        found: List[str] = []
        for prov in PROVINCES:
            try:
                (rows_json, head), scheme = _fetch_json_with_fallback(key, prov, 1, rows, timeout)
                dbg.setdefault("scanned", []).append({"prov": prov, "count": len(rows_json), "scheme": scheme})
                if rows_json:
                    found.extend(_filter_codes(rows_json, q))
                if found:
                    return sorted(set(found)), dbg
            except Exception as e:
                dbg.setdefault("scan_errors", []).append({prov: repr(e)})
        return sorted(set(found)), dbg
    return [], dbg

# ------------------------ PNU 생성 ------------------------

def parse_lot(lot: str) -> tuple[int, int, int]:
    """
    lot 예시:
      '2-14' / '2' / '산 176-18' / '산176-18' / '176-0'
    반환: (san, main, sub)  -> san: 0|1, main: 본번, sub: 부번
    """
    s = (lot or "").strip()
    san = 0
    # '산 ' 프리픽스 처리
    if s.startswith("산"):
        san = 1
        s = s[1:].strip()
    # 숫자-숫자 형태 파싱
    m = re.match(r"^(\d+)(?:\s*-\s*(\d+))?$", s)
    if not m:
        raise ValueError(f"지번 형식을 해석할 수 없습니다: {lot!r}")
    main = int(m.group(1))
    sub = int(m.group(2) or 0)
    return san, main, sub

def make_pnu(region_cd: str, san: int|bool, main: int, sub: int=0) -> str:
    """
    PNU = region_cd(10) + 산여부(1:산/0:대지) + 본번(4) + 부번(4)
    """
    rc = re.sub(r"\D", "", str(region_cd))
    if len(rc) != 10:
        raise ValueError(f"region_cd 길이가 10이 아닙니다: {region_cd!r}")
    san_digit = "1" if int(bool(san)) == 1 else "0"
    return f"{rc}{san_digit}{int(main):04d}{int(sub):04d}"

# ------------------------ CLI ------------------------

def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="MOIS 법정동코드(JSON) → region_cd / PNU 생성")
    ap.add_argument("--q","--query",dest="q",required=True,
                    help="예: '서울특별시 강남구 개포동' / '양재동' / '읍내리'")
    ap.add_argument("--rows", type=int, default=1000)
    ap.add_argument("--page", type=int, default=1)
    ap.add_argument("--timeout", type=int, default=12)
    ap.add_argument("--key", dest="key", help="serviceKey(Decoding/Encoding 모두 가능). 없으면 PUBLICDATA_KEY 사용")
    ap.add_argument("--no-scan", action="store_true", help="전국 스캔 비활성화")
    ap.add_argument("--debug", action="store_true")

    # 출력 제어
    ap.add_argument("--json", action="store_true", help="JSON 배열/오브젝트로 출력")
    ap.add_argument("--first", action="store_true",
                    help="코드가 여러 개일 때 첫 번째를 사용(미지정 시 다중 결과는 에러)")

    # PNU 생성 모드
    ap.add_argument("--pnu", action="store_true", help="PNU(19자리) 생성 모드")
    ap.add_argument("--lot", help="지번: 예) '2-14' / '산 176-18' / '176' (부번 생략 가능)")

    args = ap.parse_args(list(argv) if argv is not None else None)

    key = _service_key(args.key)
    codes, dbg = fetch_region_cd(
        key=key, q=args.q, page=args.page, rows=args.rows
