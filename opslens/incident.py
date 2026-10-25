"""Correlation into incidents, root cause ranking over the dependency graph, runbooks, severity and SLA."""
from .sim import DEPS

GAP = 45
SLA = {"P1": (15, 240), "P2": (30, 480), "P3": (120, 1440)}   # response, resolution minutes
RUNBOOKS = [
    ("no space left", "Disk full", ["df -h", "du -xh / --max-depth=2 | sort -h | tail", "journalctl --vacuum-size=200M", "Free space, then confirm writes succeed"]),
    ("no such host", "DNS failure", ["cat /etc/resolv.conf", "dig idp.internal", "resolvectl status", "Restore resolver or fix the DNS record"]),
    ("packet loss", "Network loss or latency", ["ping -c 20 10.0.3.7", "mtr -rw 10.0.3.7", "ss -tan | grep 10.0.3.7", "Escalate to the network team with mtr output"]),
    ("memory pressure", "Memory pressure", ["free -m", "top -o %MEM", "dmesg | grep -i oom", "Restart the service and open a defect for the leak"]),
]


def dependents(svc):
    out, stack = set(), [svc]
    while stack:
        cur = stack.pop()
        for s, deps in DEPS.items():
            if cur in deps and s not in out:
                out.add(s); stack.append(s)
    return out


def group(alerts):
    incidents, cur = [], []
    for a in alerts:
        if cur and a["minute"] - cur[-1]["minute"] > GAP:
            incidents.append(cur); cur = []
        cur.append(a)
    if cur:
        incidents.append(cur)
    return incidents


def rank_root_cause(alerts):
    first = {}
    for a in alerts:
        first.setdefault(a["service"], a["minute"])
    affected = set(first)
    ranked = []
    for svc, m in first.items():
        upstream_ok = not (set(DEPS[svc]) & affected)
        blast = len(dependents(svc) & affected)
        ranked.append(dict(service=svc, score=(10 if upstream_ok else 0) + blast * 2 - m / 1000,
                           reason=("no affected dependency, " if upstream_ok else "has affected dependencies, ")
                           + f"{blast} affected service(s) depend on it"))
    return sorted(ranked, key=lambda r: -r["score"])


def severity(alerts, n_services):
    page = any(a["kind"] == "slo_burn_page" for a in alerts)
    return "P1" if page and n_services >= 3 else "P2" if page else "P3"


def runbook(templates):
    text = " ".join(t["template"].lower() for t in templates)
    for key, title, steps in RUNBOOKS:
        if key in text:
            return dict(title=title, steps=steps)
    return dict(title="Unclassified", steps=["Collect logs and metrics", "Escalate to the owning engineering team"])


def ticket(alerts, n_services, truth_start=None):
    sev = severity(alerts, n_services)
    opened = alerts[0]["minute"]
    resp, res = SLA[sev]
    t = dict(severity=sev, opened_minute=opened, respond_by=opened + resp, resolve_by=opened + res)
    if truth_start is not None:
        t["time_to_detect_min"] = max(0, opened - truth_start)
    return t
