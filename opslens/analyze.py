from .sim import simulate, SCENARIOS
from .detect import detect
from .logs import novel_templates
from .incident import group, rank_root_cause, ticket, runbook


def analyze(scenario):
    sim = simulate(scenario)
    alerts = detect(sim["series"])
    incidents = []
    for grp in group(alerts):
        ranked = rank_root_cause(grp)
        root = ranked[0]["service"]
        start, end = grp[0]["minute"], grp[-1]["minute"] + 10
        tpl = novel_templates(sim["logs"][root], start - 15, end)
        incidents.append(dict(alerts=grp, services=sorted({a["service"] for a in grp}), root_cause=ranked,
                              log_patterns=tpl, runbook=runbook(tpl),
                              ticket=ticket(grp, len({a["service"] for a in grp}), sim["truth"]["start"])))
    s = sim["series"]
    return dict(scenario=scenario, truth=sim["truth"], incidents=incidents,
                chart={k: dict(err=[round(e * 100, 2) for e in v["err"]], lat=[round(x) for x in v["lat"]]) for k, v in s.items()},
                scenarios=list(SCENARIOS))
