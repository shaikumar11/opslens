import socket, threading, unittest
from http.server import HTTPServer, BaseHTTPRequestHandler
from opslens.sim import simulate, SCENARIOS
from opslens.detect import burn, burn_alerts, ewma_alerts
from opslens.logs import template, novel_templates
from opslens.incident import group, rank_root_cause, dependents, severity
from opslens.analyze import analyze
from opslens.netdiag import diagnose


class Burn(unittest.TestCase):
    def test_burn_rate_math(self):
        # 1 percent errors against a 99.9 percent SLO burns budget at 10x
        self.assertAlmostEqual(burn([1000] * 10, [10] * 10, 9, 10), 10.0, places=6)

    def test_no_alert_on_healthy_traffic(self):
        s = simulate("db_disk_full")["series"]
        healthy = {k: dict(total=v["total"][:200], errors=v["errors"][:200]) for k, v in s.items()}
        self.assertEqual(burn_alerts(healthy), [])

    def test_short_blip_does_not_page(self):
        total, errors = [1000] * 120, [0] * 120
        errors[60] = 500                 # one bad minute: long window stays under threshold
        self.assertEqual([a for a in burn_alerts({"x": dict(total=total, errors=errors)}) if a["kind"] == "slo_burn_page"], [])

    def test_ewma_flags_latency_jump(self):
        lat = [40.0 + (i % 3) for i in range(60)] + [400.0] * 5
        a = ewma_alerts({"x": dict(lat=lat)}, "lat", "latency_anomaly")
        self.assertEqual(len(a), 1); self.assertGreaterEqual(a[0]["minute"], 60)


class Logs(unittest.TestCase):
    def test_template_masks_variables(self):
        self.assertEqual(template("GET /v1/items/42 200 19ms client 10.0.1.5"), "GET /v1/items/<n> <n> <n>ms client <ip>")

    def test_novel_templates_only_new(self):
        lines = [(1, "INFO ok 5ms"), (2, "INFO ok 7ms"), (10, "INFO ok 9ms"), (10, "ERROR disk full on 3")]
        out = novel_templates(lines, 5, 20)
        self.assertEqual([o["template"] for o in out], ["ERROR disk full on <n>"])


class Incidents(unittest.TestCase):
    def test_dependents_transitive(self):
        self.assertEqual(dependents("db"), {"auth", "api", "web"})

    def test_root_cause_prefers_deepest_upstream(self):
        al = [dict(service="web", minute=5), dict(service="api", minute=5), dict(service="db", minute=6)]
        self.assertEqual(rank_root_cause(al)[0]["service"], "db")

    def test_grouping_by_gap(self):
        al = [dict(minute=10), dict(minute=20), dict(minute=200)]
        self.assertEqual([len(g) for g in group(al)], [2, 1])

    def test_severity(self):
        self.assertEqual(severity([dict(kind="slo_burn_page")], 4), "P1")
        self.assertEqual(severity([dict(kind="latency_anomaly")], 1), "P3")


class EndToEnd(unittest.TestCase):
    def test_every_scenario_finds_the_true_root_cause(self):
        for name in SCENARIOS:
            r = analyze(name)
            self.assertEqual(len(r["incidents"]), 1, name)
            self.assertEqual(r["incidents"][0]["root_cause"][0]["service"], r["truth"]["service"], name)
            self.assertLessEqual(r["incidents"][0]["ticket"]["time_to_detect_min"], 10, name)

    def test_runbook_matches_fault(self):
        titles = {n: analyze(n)["incidents"][0]["runbook"]["title"] for n in SCENARIOS}
        self.assertEqual(titles["db_disk_full"], "Disk full")
        self.assertEqual(titles["auth_dns_failure"], "DNS failure")
        self.assertEqual(titles["api_memory_leak"], "Memory pressure")


class NetDiag(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class OK(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
            def log_message(self, *a): pass
        cls.srv = HTTPServer(("127.0.0.1", 0), OK)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_healthy(self):
        self.assertEqual(diagnose("127.0.0.1", self.port)["verdict"], "Healthy")

    def test_dns_failure(self):
        self.assertEqual(diagnose("no-such-host.invalid", 80)["verdict"], "DNS resolution failed")

    def test_port_closed(self):
        s = socket.socket(); s.bind(("127.0.0.1", 0)); free = s.getsockname()[1]; s.close()
        self.assertEqual(diagnose("127.0.0.1", free)["verdict"], "Host reachable but port closed")


if __name__ == "__main__":
    unittest.main()
