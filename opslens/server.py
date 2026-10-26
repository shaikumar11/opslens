import ipaddress
import json
import os
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from .analyze import analyze
from .sim import SCENARIOS
from .netdiag import diagnose

STATIC = os.path.join(os.path.dirname(__file__), "static", "index.html")


def check_host(host):
    """Return (True, "") if every resolved address is public, else (False, reason).

    Stops the public site being used to probe private or internal addresses.
    """
    try:
        addrs = {a[4][0] for a in socket.getaddrinfo(host, None)}
    except (socket.gaierror, UnicodeError):
        return False, "could not resolve that host name"
    if not addrs:
        return False, "could not resolve that host name"
    for addr in addrs:
        ip = ipaddress.ip_address(addr.split("%")[0])
        if ip.is_multicast or not ip.is_global:
            return False, f"{host} resolves to a non public address ({ip})"
    return True, ""


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
            host = q.get("host", [""])[0].strip()
            try:
                port = int(q.get("port", ["80"])[0])
            except ValueError:
                return self._send(400, {"error": "bad port"})
            if not 1 <= port <= 65535:
                return self._send(400, {"error": "port must be between 1 and 65535"})
            if not host:
                return self._send(400, {"error": "host required"})
            ok, reason = check_host(host)
            if not ok:
                return self._send(400, {"error": reason})
            return self._send(200, diagnose(host, port))
        self._send(404, {"error": "not found"})

    def log_message(self, *a):
        pass


def main():
    # Render sets PORT. Locally you can still pass a port as an argument.
    on_render = bool(os.environ.get("PORT"))
    port = int(os.environ.get("PORT") or (sys.argv[1] if len(sys.argv) > 1 else 8000))
    host = "0.0.0.0" if on_render else "127.0.0.1"
    shown = "localhost" if host == "127.0.0.1" else host
    print(f"OpsLens running at http://{shown}:{port}")
    ThreadingHTTPServer((host, port), H).serve_forever()


if __name__ == "__main__":
    main()