# region.py — JSON 전용 CLI (HTTPS→HTTP 폴백, 전국 스캔 옵션, 표준 라이브러리만)
from __future__ import annotations
import argparse, json, os, re, sys, time
import urllib.parse as up, urllib.request as ur
from typing import Any, Iterable, List, Tuple, Optional

HTTP_URL  = "http://apis.data.go.kr/1741000/StanReginCd/getStanReginCdList"
HTTPS_URL = "https://apis.data.go.kr/1741000/StanReginCd/getStanReginCdList"

PROVINCES = [
    "서울특별시","부산광역시","대구광역시","인천광역시","광주광역시","대전광역시","울산광역시",
    "세종특별자치시","경기도","강원특별자치도","강원도","충청북도","충청남도",
    "전북특별자치도","전라북도","전라남도","경상북도","경상남도","제주특별자치도"
]

# ------------------------ 공공데이터 호출 ------------------------

def _service_key(cli_key: Optional[str]) -> str:
    key = (cli_key or os.getenv("PUBLICDATA_KEY") or "").strip()
    if not key:
        print("ERROR: serviceKey 필요 — --key 또는 PUBLICDATA_KEY", file=sys.stderr)
        raise SystemExit(3)
    # 인코딩/디코딩 키 모두 허용
    return key if "%" in key else up.quote(key, safe="")

def _http_get(url: str, timeout: int) -> bytes:
    req = ur.Request(url, headers={"User-Agent": "region-cd/stdlib-json/1.4"})
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
        # 일부 응답은 locatadd_nm, 일부는 locallow_nm만 맞을 수 있음 — 둘 다 검색
        hay = f"{r.get('locatadd_nm','')} {r.get('locallow_nm','')}"
        if all(t in hay for t in tokens):
            rc = r.get("region_cd")
            if rc:
                rc = re.sub(r"\D", "", str(rc))
                if len(rc) == 10:
                    out.append(rc)
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
      '2-14' / '2' / '산 176-18' / '산176-18' / '176-0' / '양재동 산 1-1'
    반환: (san, main, sub)  -> san: 0|1, main: 본번, sub: 부번
    규칙:
      - 문자열 어딘가에 '산' 토큰이 있으면 san=1
      - 숫자 또는 숫자-숫자 패턴을 추출 (첫 매치 사용)
      - 부번 생략 시 0
    """
    if not lot:
        raise ValueError("지번(lot)이 비어 있습니다.")
    s = lot.strip()

    # '산' 토큰 감지 (단어 경계)
    san = 1 if re.search(r"(?:^|\s)산(?:\s|$)", s) else 0
    # 첫 '산' 토큰 제거
    s = re.sub(r"(?:^|\s)산(?:\s|$)", " ", s, count=1).strip()

    # 동/리 명칭 등 비숫자 제거하고 숫자 패턴 추출
    m = re.search(r"(\d+)(?:\s*-\s*(\d+))?", s)
    if not m:
        raise ValueError(f"지번 형식을 해석할 수 없습니다: {lot!r}")

    main = int(m.group(1))
    sub  = int(m.group(2) or 0)
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
                    help="예: '서울특별시 강남구 개포동' / '서초구 양재동' / '읍내리'")
    ap.add_argument("--rows", type=int, default=1000)
    ap.add_argument("--page", type=int, default=1)
    ap.add_argument("--timeout", type=int, default=12)
    ap.add_argument("--key", dest="key", help="serviceKey(Decoding/Encoding 모두 가능). 없으면 PUBLICDATA_KEY 사용")
    ap.add_argument("--no-scan", action="store_true", help="전국 스캔 비활성화")
    ap.add_argument("--debug", action="store_true")

    # 출력 제어
    ap.add_argument("--json", action="store_true", help="JSON 배열/오브젝트로 출력")
    ap.add_argument("--first", action="store_true",
                    help="코드가 여러 개일 때 첫 번째를 강제로 사용(미지정 시 다중 결과는 에러)")

    # PNU 생성 모드
    ap.add_argument("--pnu", action="store_true", help="PNU(19자리) 생성 모드")
    ap.add_argument("--lot", help="지번: 예) '2-14' / '산 176-18' / '176' (부번 생략 가능)")

    args = ap.parse_args(list(argv) if argv is not None else None)

    key = _service_key(args.key)
    codes, dbg = fetch_region_cd(
        key=key, q=args.q, page=args.page, rows=args.rows,
        timeout=args.timeout, scan_all=not args.no_scan, debug=args.debug
    )

    if not codes:
        msg = {"ok": False, "error": "region_cd를 찾지 못했습니다.", "query": args.q}
        if args.json:
            print(json.dumps(msg, ensure_ascii=False))
        else:
            print(f"ERROR: region_cd 없음 — query={args.q}", file=sys.stderr)
        return 2

    if args.pnu:
        if not args.lot:
            if args.json:
                print(json.dumps({"ok": False, "error": "--lot 필요"}, ensure_ascii=False))
            else:
                print("ERROR: --lot 지번이 필요합니다.", file=sys.stderr)
            return 2
        try:
            san, main, sub = parse_lot(args.lot)
        except Exception as e:
            if args.json:
                print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
            else:
                print(f"ERROR: {e}", file=sys.stderr)
            return 2

        # 다중 region_cd 처리
        if len(codes) > 1 and not args.first:
            if args.json:
                print(json.dumps({
                    "ok": False,
                    "error": "복수의 region_cd가 검색되었습니다. --first로 첫 번째를 사용하거나 질의를 구체화하세요.",
                    "candidates": codes
                }, ensure_ascii=False))
            else:
                print("ERROR: 복수 region_cd — 아래 후보 중 하나로 좁혀주세요 (또는 --first 사용)", file=sys.stderr)
                for c in codes:
                    print(c, file=sys.stderr)
            return 4

        rc = codes[0]  # --first 지정 시 또는 단일 결과
        pnu = make_pnu(rc, san, main, sub)

        if args.json:
            out = {
                "ok": True,
                "pnu": pnu,
                "len": len(pnu),
                "region_cd": rc,
                "san": int(bool(san)),
                "main": f"{int(main):04d}",
                "sub": f"{int(sub):04d}",
            }
            if args.debug:
                out["debug"] = dbg
            print(json.dumps(out, ensure_ascii=False))
        else:
            print(pnu)
        return 0

    # PNU 모드가 아니면 region_cd 목록 출력
    if args.json:
        out = {"ok": True, "region_cd": codes}
        if args.debug:
            out["debug"] = dbg
        print(json.dumps(out, ensure_ascii=False))
    else:
        for c in codes:
            print(c)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
