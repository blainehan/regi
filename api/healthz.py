from http.server import BaseHTTPRequestHandler
import json, os, time

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({
            "ok": True,
            "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "has_key": bool(os.getenv("PUBLICDATA_KEY")),
            "commit": os.getenv("VERCEL_GIT_COMMIT_SHA"),
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
