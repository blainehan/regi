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

def _service_key(cli_key: str|None) -> str:
    key = (cli_key or os.getenv("PUBLICDATA_KEY") or "").strip()
    if not key:
        print("ERROR: serviceKey 필요 — --key 또는 PUBLICDATA_KEY", file=sys.stderr)
        raise SystemExit(3)
    return key if "%" in key else up.quote(key, safe="")

def _http_get(url: str, timeout: int) -> bytes:
    req = ur.Request(url, headers={"User-Agent": "region-cd/stdlib-json/1.2"})
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

def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="MOIS 법정동코드(JSON) → region_cd만 출력")
    ap.add_argument("--q","--query",dest="q",required=True,help="예: 서울특별시 서초구 양재동 / 읍내리")
    ap.add_argument("--rows", type=int, default=1000)
    ap.add_argument("--page", type=int, default=1)
    ap.add_argument("--timeout", type=int, default=12)
    ap.add_argument("--key", dest="key", help="serviceKey(Decoding/Encoding 모두 가능). 없으면 PUBLICDATA_KEY 사용")
    ap.add_argument("--no-scan", action="store_true", help="전국 스캔 비활성화")
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--json", action="store_true", help="JSON 배열로 출력")
    args = ap.parse_args(list(argv) if argv is not None else None)

    key = _service_key(args.key)
    codes, dbg = fetch_region_cd(
        key=key, q=args.q, page=args.page, rows=args.rows,
        timeout=args.timeout, scan_all=not args.no_scan, debug=args.debug
    )

    if args.json:
        print(json.dumps(sorted(set(codes)), ensure_ascii=False))
    else:
        for c in sorted(set(codes)):
            print(c)

    if not codes and args.debug:
        print("\n# DEBUG", file=sys.stderr)
        print(json.dumps(dbg, ensure_ascii=False, indent=2), file=sys.stderr)

    return 0 if codes else 2

if __name__ == "__main__":
    raise SystemExit(main())
