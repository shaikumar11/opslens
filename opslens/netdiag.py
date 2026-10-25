"""Layered network diagnosis with real DNS, TCP and HTTP checks. Names the first failing layer."""
import socket, time, http.client


def _ms(t0):
    return round((time.perf_counter() - t0) * 1000, 1)


def diagnose(host, port=80, timeout=3.0, path="/"):
    steps = []
    t0 = time.perf_counter()
    try:
        ip = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)[0][4][0]
        steps.append(dict(layer="DNS", ok=True, ms=_ms(t0), detail=f"{host} resolved to {ip}"))
    except socket.gaierror as e:
        steps.append(dict(layer="DNS", ok=False, ms=_ms(t0), detail=str(e)))
        return dict(steps=steps, verdict="DNS resolution failed",
                    fix="Check /etc/resolv.conf, run dig or nslookup, verify the record exists and the resolver is reachable.")
    t0 = time.perf_counter()
    try:
        socket.create_connection((ip, port), timeout=timeout).close()
        steps.append(dict(layer="TCP", ok=True, ms=_ms(t0), detail=f"connected to {ip}:{port}"))
    except ConnectionRefusedError:
        steps.append(dict(layer="TCP", ok=False, ms=_ms(t0), detail="connection refused"))
        return dict(steps=steps, verdict="Host reachable but port closed",
                    fix="Service is not listening. Check the process with ss -ltnp and the service status.")
    except (socket.timeout, TimeoutError, OSError) as e:
        steps.append(dict(layer="TCP", ok=False, ms=_ms(t0), detail=f"timeout or unreachable: {e}"))
        return dict(steps=steps, verdict="No route or traffic dropped",
                    fix="Likely firewall, security group or routing. Run traceroute or mtr and check rules.")
    t0 = time.perf_counter()
    try:
        c = http.client.HTTPConnection(ip, port, timeout=timeout)
        c.request("GET", path, headers={"Host": host})
        status = c.getresponse().status
        c.close()
        ok = status < 500
        steps.append(dict(layer="HTTP", ok=ok, ms=_ms(t0), detail=f"status {status}"))
        return dict(steps=steps, verdict="Healthy" if ok else "Application error",
                    fix="" if ok else "Network is fine, the application returned a server error. Check app logs.")
    except Exception as e:
        steps.append(dict(layer="HTTP", ok=False, ms=_ms(t0), detail=str(e)))
        return dict(steps=steps, verdict="Application not responding", fix="Port is open but HTTP failed. Check the app and logs.")
