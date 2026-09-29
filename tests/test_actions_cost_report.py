import datetime as dt
import io
import json
import os
import unittest
from contextlib import redirect_stdout

from helpers import FIXTURES, load_script

report_mod = load_script("actions-cost-report")


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


class ActionsCostReportTest(unittest.TestCase):
    def setUp(self):
        self.report = report_mod.build_report(
            fixture("billing-usage.json"), fixture("billing-budgets.json"), fixture("visibility.json"),
            2026, 9, today=dt.date(2026, 9, 10))

    def test_totals_split_gross_and_net(self):
        self.assertAlmostEqual(self.report["totals"]["net"], 16.36, places=2)
        self.assertAlmostEqual(self.report["by_product"]["ghec"]["net"], 7.0, places=2)
        self.assertAlmostEqual(self.report["by_product"]["actions"]["net"], 9.36, places=2)
        self.assertGreater(self.report["totals"]["gross"], self.report["totals"]["net"])

    def test_private_repos_ranked_by_net_and_exclude_public(self):
        names = [row["repo"] for row in self.report["private_repos"]]
        self.assertEqual(names, ["private-app", "private-site", "private-idle"])
        self.assertAlmostEqual(self.report["private_repos"][0]["net"], 7.26, places=2)
        self.assertEqual(self.report["private_repos"][0]["minutes"], 3100)

    def test_repo_sku_rows(self):
        rows = [(row["repo"], row["sku"]) for row in self.report["repo_sku"]]
        self.assertEqual(rows[:2], [("(organization)", "Enterprise Cloud"), ("private-app", "Actions Linux")])
        self.assertAlmostEqual(self.report["repo_sku"][1]["net"], 5.4, places=2)

    def test_daily_trend_excludes_today_from_the_average(self):
        daily = {row["date"]: row["net"] for row in self.report["daily_net"]}
        self.assertAlmostEqual(daily["2026-09-07"], 0.7, places=2)
        self.assertAlmostEqual(daily["2026-09-08"], 3.82, places=2)
        # complete days 09-03..09-09: five at 0.70 and two at 3.82
        self.assertAlmostEqual(self.report["trend"]["avg_7d_net"], (5 * 0.7 + 2 * 3.82) / 7, places=2)
        self.assertAlmostEqual(self.report["trend"]["avg_3d_net"], (0.7 + 2 * 3.82) / 3, places=2)
        self.assertEqual(self.report["trend"]["remaining_days"], 20)

    def test_budget_headroom(self):
        actions = next(b for b in self.report["budgets"] if b["sku"] == "actions")
        self.assertAlmostEqual(actions["headroom"], 10.64, places=2)
        self.assertTrue(actions["prevent_further_usage"])
        self.assertIsNotNone(actions["days_left_at_7d_rate"])
        codespaces = next(b for b in self.report["budgets"] if b["sku"] == "codespaces")
        self.assertEqual(codespaces["days_left_at_7d_rate"], 0.0)

    def test_visibility_inferred_from_net_without_visibility_data(self):
        report = report_mod.build_report(fixture("billing-usage.json"), None, None, 2026, 9, today=dt.date(2026, 9, 10))
        self.assertTrue(report["visibility_inferred"])
        self.assertEqual([row["repo"] for row in report["private_repos"]], ["private-app", "private-site"])

    def test_cli_markdown_and_json(self):
        args = ["--year", "2026", "--month", "9", "--usage-file", str(FIXTURES / "billing-usage.json"),
                "--budgets-file", str(FIXTURES / "billing-budgets.json"), "--visibility-file", str(FIXTURES / "visibility.json")]
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(report_mod.main(args), 0)
        text = out.getvalue()
        self.assertIn("**net $16.36**", text)
        self.assertIn("## Private repositories", text)
        self.assertIn("## Budgets", text)
        out = io.StringIO()
        with redirect_stdout(out):
            report_mod.main(args + ["--json"])
        self.assertAlmostEqual(json.loads(out.getvalue())["totals"]["net"], 16.36, places=2)

    def test_money_formats_negative_values(self):
        self.assertEqual(report_mod.money(-77.4), "-$77.40")
        self.assertEqual(report_mod.money(1234.5), "$1,234.50")

    @unittest.skipUnless(os.environ.get("BILLING_USAGE_FILE"), "set BILLING_USAGE_FILE to a saved billing/usage response")
    def test_saved_billing_export(self):
        usage = json.loads(open(os.environ["BILLING_USAGE_FILE"]).read())
        report = report_mod.build_report(usage, None, None, 2026, 9)
        self.assertAlmostEqual(report["totals"]["net"], sum(i["netAmount"] for i in usage["usageItems"]), places=2)
        nets = [row["net"] for row in report["private_repos"]]
        self.assertEqual(nets, sorted(nets, reverse=True))
        expected = os.environ.get("BILLING_EXPECT_NET")
        if expected:
            self.assertAlmostEqual(report["totals"]["net"], float(expected), places=2)


if __name__ == "__main__":
    unittest.main()
