"""Layered network diagnosis with real DNS, TCP and HTTP checks. Names the first failing layer.

The HTTP step uses HTTPS on port 443 and 8443 and plain HTTP on every other port.
"""
import http.client
import ipaddress
import socket
import ssl
import time

HTTPS_PORTS = (443, 8443)


def _ms(t0):
    return round((time.perf_counter() - t0) * 1000, 1)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Connects to an IP we already resolved, but verifies the certificate for the host name.

    This keeps the TCP step and the HTTP step on the same address.
    """

    def __init__(self, ip, port, host, timeout, context):
        super().__init__(ip, port, timeout=timeout, context=context)
        self._sni_host = host
        self._tls_context = context

    def connect(self):
        sock = socket.create_connection((self.host, self.port), self.timeout)
        self.sock = self._tls_context.wrap_socket(sock, server_hostname=self._sni_host)


def _fail(steps, layer, t0, detail, verdict, fix):
    steps.append(dict(layer=layer, ok=False, ms=_ms(t0), detail=detail))
    return dict(steps=steps, verdict=verdict, fix=fix)


def diagnose(host, port=80, timeout=4.0, path="/", allow_private=False):
    steps = []

    # DNS
    t0 = time.perf_counter()
    try:
        ip = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)[0][4][0]
    except (socket.gaierror, UnicodeError) as e:
        return _fail(steps, "DNS", t0, str(e), "DNS resolution failed",
                     "Check /etc/resolv.conf, run dig or nslookup, verify the record exists and the resolver is reachable.")
    # Defence in depth: never connect to a non public address, even if the caller forgot to check.
    if not allow_private and not ipaddress.ip_address(ip).is_global:
        return _fail(steps, "DNS", t0, f"{host} resolved to a non public address ({ip})",
                     "Non public address refused", "Only public hosts can be diagnosed from this page.")
    steps.append(dict(layer="DNS", ok=True, ms=_ms(t0), detail=f"{host} resolved to {ip}"))

    # TCP
    t0 = time.perf_counter()
    try:
        socket.create_connection((ip, port), timeout=timeout).close()
        steps.append(dict(layer="TCP", ok=True, ms=_ms(t0), detail=f"connected to {ip}:{port}"))
    except ConnectionRefusedError:
        return _fail(steps, "TCP", t0, "connection refused", "Host reachable but port closed",
                     "Service is not listening. Check the process with ss -ltnp and the service status.")
    except OSError as e:
        return _fail(steps, "TCP", t0, f"timeout or unreachable: {e}", "No route or traffic dropped",
                     "Likely firewall, security group or routing. Run traceroute or mtr and check rules.")

    # HTTP or HTTPS
    scheme = "HTTPS" if port in HTTPS_PORTS else "HTTP"
    t0 = time.perf_counter()
    conn = None
    try:
        if scheme == "HTTPS":
            conn = _PinnedHTTPSConnection(ip, port, host, timeout, ssl.create_default_context())
        else:
            conn = http.client.HTTPConnection(ip, port, timeout=timeout)
        conn.request("GET", path, headers={"Host": host, "User-Agent": "OpsLens/1.0", "Connection": "close"})
        status = conn.getresponse().status
    except ssl.SSLCertVerificationError as e:
        return _fail(steps, scheme, t0, f"certificate problem: {e.verify_message or e}",
                     "TLS certificate problem",
                     "The certificate is expired, self signed, or issued for another name. Check it with openssl s_client.")
    except ssl.SSLError as e:
        return _fail(steps, scheme, t0, f"TLS handshake failed: {e}", "TLS handshake failed",
                     "Check the TLS versions and ciphers the service accepts, and that this port really serves HTTPS.")
    except (socket.timeout, TimeoutError):
        return _fail(steps, scheme, t0, "request timed out", "Application not responding",
                     "The port accepts connections but the app does not answer in time. Check load, threads and logs.")
    except (http.client.HTTPException, OSError) as e:
        hint = "If this port serves HTTPS, use 443 or 8443. " if scheme == "HTTP" else ""
        return _fail(steps, scheme, t0, str(e) or type(e).__name__, "Application not responding",
                     hint + "Port is open but the web request failed. Check the app and logs.")
    finally:
        if conn is not None:
            conn.close()

    ok = status < 500
    steps.append(dict(layer=scheme, ok=ok, ms=_ms(t0), detail=f"status {status}"))
    if ok:
        verdict = "Healthy" if status < 400 else f"Reachable, the app returned {status}"
        return dict(steps=steps, verdict=verdict,
                    fix="" if status < 400 else "Network is fine. A 4xx status usually means the path or credentials are wrong.")
    return dict(steps=steps, verdict="Application error",
                fix="Network is fine, the application returned a server error. Check app logs.")