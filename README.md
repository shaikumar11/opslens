# OpsLens

A cloud incident console. It simulates a fleet of five services with a dependency graph, injects real-world faults, then detects, correlates and triages the incident the way a support or SRE team would. Pure Python standard library, no installs.

## Run
```
python -m opslens.server
```
Open http://localhost:8000, pick a scenario and click Run scenario.

```
python -m unittest discover -s tests
```

## What it does
| Stage | How it works |
|---|---|
| Simulation | web, api, auth, cache and db services with dependencies. Faults: disk full, DNS failure, cache packet loss, memory leak. Errors and latency propagate to dependents |
| Detection | Multi-window burn-rate alerts against a 99.9 percent SLO (page at 14.4x over 1h and 5m, ticket at 6x over 6h and 30m), plus EWMA anomaly detection for latency and CPU |
| Log analysis | Masks IPs and numbers into templates, then shows patterns that are new during the incident |
| Correlation | Groups alerts into one incident and ranks root cause: services with no affected dependency and the largest blast radius rank first |
| Ticket | Severity P1 to P3, response and resolution deadlines, time to detect |
| Runbook | Matches log patterns to a fault and lists Linux commands to run |
| Network diagnosis | Real DNS, TCP and HTTP checks that name the first failing layer |

## Tests
15 unit tests cover burn-rate maths, no false page on a one-minute blip, anomaly detection, log templates, root cause ranking, and an end-to-end check that every scenario finds the true faulty service within 10 minutes. Network diagnosis is tested against a local server, a closed port and an invalid host.

## Notes
All data is simulated. Services, faults and logs are synthetic.
