"""Deterministic fleet simulator: 5 services, a dependency graph, injected faults, metrics and logs."""
import random

DEPS = {"web": ["api"], "api": ["db", "cache", "auth"], "auth": ["db"], "cache": [], "db": []}
ORDER = ["db", "cache", "auth", "api", "web"]   # dependencies first
MINUTES = 360
BASE_ERR, BASE_LAT, BASE_CPU = 0.0005, 40.0, 30.0

SCENARIOS = {
    "db_disk_full": dict(service="db", start=240, dur=50, err=0.6, lat=800, cpu=10, ramp=False,
        log="ERROR could not write block {n} in file base/16384/{n}: No space left on device"),
    "auth_dns_failure": dict(service="auth", start=200, dur=40, err=0.9, lat=300, cpu=0, ramp=False,
        log="ERROR dial tcp: lookup idp.internal on 10.0.0.2:53: no such host"),
    "cache_latency": dict(service="cache", start=220, dur=60, err=0.02, lat=500, cpu=5, ramp=False,
        log="WARN cache timeout after {n}ms host 10.0.3.7 packet loss detected"),
    "api_memory_leak": dict(service="api", start=180, dur=120, err=0.15, lat=900, cpu=55, ramp=True,
        log="WARN GC pause {n}ms heap 91 percent, memory pressure rising"),
}
NORMAL = ["INFO GET /v1/items/{n} 200 {m}ms client 10.0.{a}.{b}", "INFO health check ok latency {m}ms",
          "INFO cache hit ratio 0.{n}"]


def simulate(scenario, seed=7):
    rng = random.Random(seed)
    sc = SCENARIOS[scenario]
    s = {k: dict(total=[], errors=[], lat=[], cpu=[], err=[]) for k in DEPS}
    logs = {k: [] for k in DEPS}
    for t in range(MINUTES):
        for svc in ORDER:
            d = s[svc]
            f = 0.0
            if svc == sc["service"] and sc["start"] <= t < sc["start"] + sc["dur"]:
                f = (t - sc["start"] + 1) / sc["dur"] if sc["ramp"] else 1.0
            err = BASE_ERR + sc["err"] * f
            lat = BASE_LAT + rng.gauss(0, 2) + sc["lat"] * f
            cpu = BASE_CPU + rng.gauss(0, 1.5) + sc["cpu"] * f
            up_err = 0.0
            for dep in DEPS[svc]:
                e = s[dep]["err"][t] - BASE_ERR
                up_err = max(up_err, 0.7 * e)
                lat += 0.6 * (s[dep]["lat"][t] - BASE_LAT)
            err = min(1.0, err + up_err)
            total = int(1000 + rng.gauss(0, 25))
            d["total"].append(total); d["errors"].append(int(total * err))
            d["lat"].append(lat); d["cpu"].append(cpu); d["err"].append(err)
            for _ in range(3):
                logs[svc].append((t, rng.choice(NORMAL).format(n=rng.randint(1, 9999), m=rng.randint(5, 60),
                                                              a=rng.randint(0, 9), b=rng.randint(1, 250))))
            if f > 0:
                for _ in range(2 + int(f * 3)):
                    logs[svc].append((t, sc["log"].format(n=rng.randint(100, 9999))))
            elif up_err > 0.05:
                dep = [x for x in DEPS[svc] if s[x]["err"][t] - BASE_ERR > 0.05][0]
                logs[svc].append((t, f"ERROR upstream {dep} returned 503 after {rng.randint(300, 900)}ms"))
    return dict(series=s, logs=logs, truth=dict(service=sc["service"], start=sc["start"], dur=sc["dur"]))
