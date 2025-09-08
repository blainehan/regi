#!/usr/bin/env python3
# region.py — MOIS region_cd / PNU 생성기 (서비스키는 --key 또는 환경변수 사용)

import argparse, json, os, re, sys, time
import urllib.parse as up, urllib.request as ur
from typing import Any, Iterable, List, Tuple, Optional

# ------------------------ 공공데이터 호출 ------------------------

def _service_key(cli_key: Optional[str]) -> str:
    key = (cli_key or os.getenv("PUBLICDATA_KEY") or "").strip()
    if not key:
        print("ERROR: serviceKey 필요 — --key 또는 PUBLICDATA_KEY", file=sys.stderr)
        raise SystemExit(3)
    return key if "%" in key else up.quote(key, safe="")

HTTP_URL  = "http://apis.data.go.kr/1741000/StanReginCd/getStanReginCdList"
HTTPS_URL = "https://apis.data.go.kr/1741000/StanReginCd/getStanReginCdList"

def _http_get(url: str, timeout: int) -> bytes:
    req = ur.Request(url, headers={"User-Agent": "region-cd/1.0"})
    with ur.urlopen(req, timeout=timeout) as r:
        return r.read()

def _rows_from_json(data: Any) -> Tuple[list, dict]:
    rows, head = [], {}
    blocks = data.get("StanReginCd", [])
    for b in blocks:
        if isinstance(b, dict):
            if isinstance(b.get("row"), list):
                rows.extend([x for x in b["row"] if isinstance(x, dict)])
            if isinstance(b.get("head"), list) and b["head"]:
                head = b["head"][0]
    return rows, head

def _fetch_region_rows(key: str, q: str, page=1, rows=1000, timeout=10):
    for base_url in [HTTPS_URL, HTTP_URL]:
        qs = f"serviceKey={key}&pageNo={page}&numOfRows={rows}&type=JSON&locatadd_nm={up.quote(q)}"
        url = f"{base_url}?{qs}"
        try:
            raw = _http_get(url, timeout)
            data = json.loads(raw.decode("utf-8"))
            return _rows_from_json(data)
        except Exception:
            continue
    raise RuntimeError("API 요청 실패")

def _filter_codes(rows: list, query: str) -> list[str]:
    tokens = [t for t in re.split(r"\s+", query.strip()) if t]
    out = []
    for r in rows:
        hay = f"{r.get('locatadd_nm','')} {r.get('locallow_nm','')}"
        if all(t in hay for t in tokens):
            rc = r.get("region_cd")
            if rc and len(re.sub(r"\D", "", rc)) == 10:
                out.append(re.sub(r"\D", "", rc))
    return sorted(set(out))

def parse_lot(lot: str) -> tuple[int, int, int]:
    s = lot.strip()
    san = 1 if re.search(r"(?:^|\s)산(?:\s|$)", s) else 0
    s = re.sub(r"(?:^|\s)산(?:\s|$)", " ", s, count=1).strip()
    m = re.search(r"(\d+)(?:\s*-\s*(\d+))?", s)
    if not m:
        raise ValueError(f"지번 형식을 해석할 수 없습니다: {lot!r}")
    main = int(m.group(1))
    sub  = int(m.group(2) or 0)
    return san, main, sub

def make_pnu(region_cd: str, san: int, main: int, sub: int) -> str:
    return f"{region_cd}{san}{main:04d}{sub:04d}"

def main():
    ap = argparse.ArgumentParser(description="MOIS region_cd / PNU 생성기")
    ap.add_argument("--q", required=True, help="예: '서초구 양재동'")
    ap.add_argument("--key", help="공공데이터포털 서비스키 (생략 시 PUBLICDATA_KEY 환경변수 사용)")
    ap.add_argument("--pnu", action="store_true", help="PNU 생성 모드")
    ap.add_argument("--lot", help="지번 예: '산 2-14', '123-1', '88'")
    args = ap.parse_args()

    key = _service_key(args.key)
    rows, _ = _fetch_region_rows(key, args.q)
    codes = _filter_codes(rows, args.q)

    if not codes:
        print("ERROR: region_cd 없음", file=sys.stderr)
        return 2

    region_cd = codes[0]

    if args.pnu:
        if not args.lot:
            print("ERROR: --lot 지번이 필요합니다", file=sys.stderr)
            return 2
        try:
            san, main, sub = parse_lot(args.lot)
            pnu = make_pnu(region_cd, san, main, sub)
            print(pnu)
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 3
    else:
        print(region_cd)

if __name__ == "__main__":
    main()
