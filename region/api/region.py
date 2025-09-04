from http.server import BaseHTTPRequestHandler
import json, os, urllib.parse as up, urllib.request as ur

HTTP_URL  = "http://apis.data.go.kr/1741000/StanReginCd/getStanReginCdList"
HTTPS_URL = "https://apis.data.go.kr/1741000/StanReginCd/getStanReginCdList"

def _http_get(url: str, timeout: int = 10) -> bytes:
    req = ur.Request(url, headers={"User-Agent": "regi-vercel/1.0"})
    with ur.urlopen(req, timeout=timeout) as r:
        return r.read()

def _rows_from_json(data):
    rows = []
    if isinstance(data, dict):
        blocks = data.get("StanReginCd")
        if isinstance(blocks, list):
            for b in blocks:
                if isinstance(b, dict) and isinstance(b.get("row"), list):
                    rows += [x for x in b["row"] if isinstance(x, dict)]
    return rows

def _build_qs(key: str, q: str, page: int, rows: int) -> str:
    if "%" not in key:
        key = up.quote(key, safe="")
    return f"serviceKey={key}&pageNo={page}&numOfRows={rows}&type=JSON&locatadd_nm={up.quote(q)}"

def _fetch_once(base: str, key: str, q: str, page: int, rows: int):
    raw = _http_get(f"{base}?{_build_qs(key, q, page, rows)}", timeout=10)
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        data = json.loads(raw)
    return _rows_from_json(data)

def _codes(key: str, q: str, page: int, rows: int):
    rows_json = []
    try: rows_json = _fetch_once(HTTPS_URL, key, q, page, rows)
    except Exception: pass
    if not rows_json:
        try: rows_json = _fetch_once(HTTP_URL, key, q, page, rows)
        except Exception: rows_json = []
    out = []
    for r in rows_json:
        rc = r.get("region_cd")
        if rc: out.append(str(rc))
    return sorted(set(out))

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            p = up.urlparse(self.path)
            qs = up.parse_qs(p.query)
            q     = (qs.get("q")     or qs.get("query") or [""])[0].strip()
            page  = int((qs.get("page") or ["1"])[0])
            rows  = int((qs.get("rows") or ["1000"])[0])
            key   = (qs.get("key") or [os.getenv("PUBLICDATA_KEY", "")])[0].strip()

            if not q:
                return self._json(400, {"ok": False, "error": "q required"})
            if not key:
                return self._json(400, {"ok": False, "error": "serviceKey required (env PUBLICDATA_KEY or ?key=...)"})

            codes = _codes(key, q, page, rows)
            return self._json(200, {"ok": True, "q": q, "count": len(codes), "codes": codes})
        except Exception as e:
            return self._json(500, {"ok": False, "error": repr(e)})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _json(self, status: int, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
