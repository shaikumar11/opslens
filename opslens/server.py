import json, os, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from .analyze import analyze
from .sim import SCENARIOS
from .netdiag import diagnose

STATIC = os.path.join(os.path.dirname(__file__), "static", "index.html")


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

    def do_GET(self):
        u, q = urlparse(self.path), parse_qs(urlparse(self.path).query)
        if u.path == "/":
            return self._send(200, open(STATIC, "rb").read(), "text/html")
        if u.path == "/api/run":
            name = q.get("scenario", ["db_disk_full"])[0]
            return self._send(200, analyze(name)) if name in SCENARIOS else self._send(400, {"error": "unknown scenario"})
        if u.path == "/api/netdiag":
            host = q.get("host", [""])[0]
            try:
                port = int(q.get("port", ["80"])[0])
            except ValueError:
                return self._send(400, {"error": "bad port"})
            return self._send(200, diagnose(host, port)) if host else self._send(400, {"error": "host required"})
        self._send(404, {"error": "not found"})

    def log_message(self, *a):
        pass


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"OpsLens running at http://localhost:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()


if __name__ == "__main__":
    main()
