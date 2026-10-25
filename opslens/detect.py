"""Detection: multi-window burn-rate SLO alerts (SRE workbook style) and EWMA anomaly detection."""
import math

SLO = 0.999
BUDGET = 1 - SLO
RULES = [("page", 60, 5, 14.4), ("ticket", 360, 30, 6.0)]   # kind, long window, short window, burn threshold


def burn(total, errors, t, w):
    lo = max(0, t - w + 1)
    tot = sum(total[lo:t + 1])
    return (sum(errors[lo:t + 1]) / tot) / BUDGET if tot else 0.0


def burn_alerts(series):
    out = []
    for svc, d in series.items():
        fired = set()
        for t in range(len(d["total"])):
            for kind, lw, sw, th in RULES:
                if kind in fired:
                    continue
                bl, bs = burn(d["total"], d["errors"], t, lw), burn(d["total"], d["errors"], t, sw)
                if bl > th and bs > th:
                    fired.add(kind)
                    out.append(dict(service=svc, minute=t, kind=f"slo_burn_{kind}",
                                    detail=f"burn rate {bl:.1f}x over {lw}m and {bs:.1f}x over {sw}m, threshold {th}x"))
    return out


def ewma_alerts(series, metric, label, k=4.0, alpha=0.1, warmup=30, need=3):
    out = []
    for svc, d in series.items():
        mean, var, run = d[metric][0], 1.0, 0
        for t, x in enumerate(d[metric]):
            sd = math.sqrt(var)
            if t >= warmup and x > mean + k * max(sd, 1.0):
                run += 1
                if run == need:
                    out.append(dict(service=svc, minute=t, kind=label,
                                    detail=f"{label} {x:.0f} vs baseline {mean:.0f}"))
                    break
                continue          # do not learn from anomalous points
            run = 0
            diff = x - mean
            mean += alpha * diff
            var = (1 - alpha) * (var + alpha * diff * diff)
    return out


def detect(series):
    a = burn_alerts(series) + ewma_alerts(series, "lat", "latency_anomaly") + ewma_alerts(series, "cpu", "cpu_anomaly")
    return sorted(a, key=lambda x: x["minute"])
