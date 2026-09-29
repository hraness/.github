#!/usr/bin/env python3
"""Report an organization's GitHub billing usage: where the money goes and how fast.

usage: scripts/actions-cost-report.py [--org hraness] [--year Y] [--month M] [--json]
                                      [--usage-file F] [--summary-file F] [--budgets-file F]
                                      [--visibility-file F]
                                      [--top N]

Reads the enhanced billing API with `gh api`:
  organizations/<org>/settings/billing/usage?year=&month=   (per day, repository and SKU)
  organizations/<org>/settings/billing/usage/summary?year=&month=   (per SKU, cross-check)
  organizations/<org>/settings/billing/budgets
and repository visibility from orgs/<org>/repos. The *-file options read saved
JSON instead (the same shapes the API returns; the visibility file maps
repository name to "public" or "private").

Reports gross (list price) and net (charged) per repository and SKU, the daily
net trend with a month-end projection, the private repositories that cost the
most, and headroom on each budget. Public-repository minutes on GitHub-hosted
runners are discounted in full, so net charges come from private repositories
and licenses. Without visibility data, a repository with any net charge is
reported as private (inferred).
"""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from collections import defaultdict


def gh_json(path: str) -> object:
    gh = os.environ.get("GH") or shutil.which("gh") or "gh"
    result = subprocess.run([gh, "api", "-H", "Accept: application/vnd.github+json", path], capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"gh api {path} failed: {result.stderr.strip()[:400]}")
    return json.loads(result.stdout)


def gh_paginated(path: str) -> list:
    gh = os.environ.get("GH") or shutil.which("gh") or "gh"
    result = subprocess.run([gh, "api", "--paginate", "--slurp", path], capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"gh api {path} failed: {result.stderr.strip()[:400]}")
    return [item for page in json.loads(result.stdout) for item in page]


def load(path: str) -> object:
    with open(path) as handle:
        return json.load(handle)


def money(value: float) -> str:
    return f"-${-value:,.2f}" if value < 0 else f"${value:,.2f}"


def build_report(usage: dict, budgets: dict | None, visibility: dict[str, str] | None, year: int, month: int, top: int = 15, today: dt.date | None = None, summary: dict | None = None) -> dict:
    items = usage.get("usageItems", [])
    totals = {"gross": 0.0, "discount": 0.0, "net": 0.0}
    by_product: dict[str, dict[str, float]] = defaultdict(lambda: {"gross": 0.0, "net": 0.0})
    by_repo_sku: dict[tuple[str, str], dict[str, float]] = defaultdict(lambda: {"quantity": 0.0, "gross": 0.0, "net": 0.0})
    by_repo: dict[str, dict[str, float]] = defaultdict(lambda: {"minutes": 0.0, "gross": 0.0, "net": 0.0})
    daily: dict[str, float] = defaultdict(float)
    daily_product: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for item in items:
        gross, net = float(item.get("grossAmount", 0)), float(item.get("netAmount", 0))
        totals["gross"] += gross
        totals["discount"] += float(item.get("discountAmount", 0))
        totals["net"] += net
        product = item.get("product", "")
        by_product[product]["gross"] += gross
        by_product[product]["net"] += net
        repo = item.get("repositoryName") or "(organization)"
        sku = item.get("sku", "")
        cell = by_repo_sku[(repo, sku)]
        cell["quantity"] += float(item.get("quantity", 0))
        cell["gross"] += gross
        cell["net"] += net
        by_repo[repo]["gross"] += gross
        by_repo[repo]["net"] += net
        if str(item.get("unitType", "")).lower() == "minutes":
            by_repo[repo]["minutes"] += float(item.get("quantity", 0))
        daily[str(item.get("date", ""))[:10]] += net
        daily_product[product][str(item.get("date", ""))[:10]] += net

    inferred = visibility is None
    def is_private(repo: str) -> bool:
        if repo == "(organization)":
            return False
        if visibility is not None:
            return visibility.get(repo) == "private"
        return by_repo[repo]["net"] > 0

    days_in_month = calendar.monthrange(year, month)[1]
    dates = sorted(d for d in daily if d)
    today = today or dt.datetime.now(dt.timezone.utc).date()
    # Today's usage is still accruing; average complete days only.
    complete = [d for d in dates if d != today.isoformat()]
    def avg_last7(series: dict[str, float], days: int = 7) -> float:
        window = complete[-days:]
        return sum(series.get(d, 0.0) for d in window) / len(window) if window else 0.0
    avg7 = avg_last7(daily)
    last_day = dt.date.fromisoformat(dates[-1]) if dates else dt.date(year, month, 1)
    in_month = (today.year, today.month) == (year, month)
    remaining = max(0, days_in_month - last_day.day) if in_month else 0
    projection = totals["net"] + avg7 * remaining

    spend_by_budget_sku = {"actions": by_product.get("actions", {}).get("net", 0.0)}
    for product, cell in by_product.items():
        spend_by_budget_sku.setdefault(product, cell["net"])
    budget_rows = []
    for budget in (budgets or {}).get("budgets", []):
        sku = budget.get("budget_product_sku") or budget.get("budget_type")
        spent = spend_by_budget_sku.get(sku, 0.0)
        rate = avg_last7(daily_product.get(sku, {}))
        amount = float(budget.get("budget_amount", 0))
        budget_rows.append({
            "sku": sku,
            "scope": budget.get("budget_scope"),
            "amount": amount,
            "spent": round(spent, 2),
            "headroom": round(amount - spent, 2),
            "used_pct": round(100 * spent / amount, 1) if amount else None,
            "prevent_further_usage": bool(budget.get("prevent_further_usage")),
            "avg_7d_net": round(rate, 2),
            "days_left_at_7d_rate": 0.0 if spent >= amount else (round((amount - spent) / rate, 1) if rate > 0 else None),
        })

    private = sorted(((repo, cell) for repo, cell in by_repo.items() if is_private(repo)), key=lambda rc: (-rc[1]["net"], -rc[1]["minutes"], rc[0]))
    repo_sku = sorted(({"repo": r, "sku": s, **{k: round(v, 3) for k, v in c.items()}} for (r, s), c in by_repo_sku.items()), key=lambda row: (-row["net"], -row["gross"], row["repo"], row["sku"]))
    return {
        "period": {"year": year, "month": month, "first_day": dates[0] if dates else None, "last_day": dates[-1] if dates else None},
        "totals": {k: round(v, 2) for k, v in totals.items()},
        "by_product": {p: {k: round(v, 2) for k, v in c.items()} for p, c in sorted(by_product.items())},
        "repo_sku": repo_sku[: max(top * 2, top)],
        "daily_net": [{"date": d, "net": round(daily[d], 2)} for d in dates],
        "trend": {"avg_3d_net": round(avg_last7(daily, 3), 2), "avg_7d_net": round(avg7, 2), "projected_month_net": round(projection, 2), "remaining_days": remaining},
        "private_repos": [{"repo": r, "minutes": round(c["minutes"]), "gross": round(c["gross"], 2), "net": round(c["net"], 2)} for r, c in private[:top]],
        "visibility_inferred": inferred,
        "budgets": budget_rows,
        "summary_net": round(sum(float(i.get("netAmount", 0)) for i in summary.get("usageItems", [])), 2) if summary else None,
    }


def markdown(report: dict) -> str:
    p, t = report["period"], report["totals"]
    out = [f"# GitHub billing {p['year']}-{p['month']:02d}", ""]
    out.append(f"Usage {p['first_day']} to {p['last_day']}: gross {money(t['gross'])}, discount {money(t['discount'])}, **net {money(t['net'])}**.")
    if report["summary_net"] is not None and abs(report["summary_net"] - t["net"]) >= 0.01:
        out.append(f"The billing summary endpoint reports net {money(report['summary_net'])}; the per-day usage and the summary are updated at different times.")
    tr = report["trend"]
    out.append(f"Net per day over the last 3 complete days {money(tr['avg_3d_net'])}, last 7 {money(tr['avg_7d_net'])}; projected month net {money(tr['projected_month_net'])} ({tr['remaining_days']} days left).")
    out += ["", "## By product", "", "| product | gross | net |", "|---|---:|---:|"]
    out += [f"| {name} | {money(c['gross'])} | {money(c['net'])} |" for name, c in report["by_product"].items()]
    label = "Private repositories (inferred from net charges)" if report["visibility_inferred"] else "Private repositories"
    out += ["", f"## {label}", "", "| repository | minutes | gross | net |", "|---|---:|---:|---:|"]
    out += [f"| {r['repo']} | {r['minutes']:,} | {money(r['gross'])} | {money(r['net'])} |" for r in report["private_repos"]]
    out += ["", "## Repository x SKU", "", "| repository | SKU | quantity | gross | net |", "|---|---|---:|---:|---:|"]
    out += [f"| {r['repo']} | {r['sku']} | {r['quantity']:,.0f} | {money(r['gross'])} | {money(r['net'])} |" for r in report["repo_sku"]]
    out += ["", "## Daily net", "", "| date | net |", "|---|---:|"]
    out += [f"| {d['date']} | {money(d['net'])} |" for d in report["daily_net"]]
    if report["budgets"]:
        out += ["", "## Budgets", "", "| SKU | budget | spent | headroom | used | stops usage | days left at 7-day rate |", "|---|---:|---:|---:|---:|---|---:|"]
        for b in report["budgets"]:
            used = "" if b["used_pct"] is None else f"{b['used_pct']}%"
            days = "" if b["days_left_at_7d_rate"] is None else f"{b['days_left_at_7d_rate']}"
            out.append(f"| {b['sku']} | {money(b['amount'])} | {money(b['spent'])} | {money(b['headroom'])} | {used} | {'yes' if b['prevent_further_usage'] else 'no'} | {days} |")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    now = dt.datetime.now(dt.timezone.utc)
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--org", default="hraness")
    ap.add_argument("--year", type=int, default=now.year)
    ap.add_argument("--month", type=int, default=now.month, choices=range(1, 13), metavar="MONTH")
    ap.add_argument("--usage-file")
    ap.add_argument("--summary-file")
    ap.add_argument("--budgets-file")
    ap.add_argument("--visibility-file")
    ap.add_argument("--no-budgets", action="store_true", help="skip the budgets API")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    usage = load(a.usage_file) if a.usage_file else gh_json(f"organizations/{a.org}/settings/billing/usage?year={a.year}&month={a.month}")
    summary = load(a.summary_file) if a.summary_file else (None if a.usage_file else gh_json(f"organizations/{a.org}/settings/billing/usage/summary?year={a.year}&month={a.month}"))
    budgets = None
    if a.budgets_file:
        budgets = load(a.budgets_file)
    elif not a.no_budgets and not a.usage_file:
        budgets = gh_json(f"organizations/{a.org}/settings/billing/budgets")
    if a.visibility_file:
        visibility = load(a.visibility_file)
    elif a.usage_file:
        visibility = None
    else:
        visibility = {r["name"]: r.get("visibility", "private" if r.get("private") else "public") for r in gh_paginated(f"orgs/{a.org}/repos?type=all&per_page=100")}
    report = build_report(usage, budgets, visibility, a.year, a.month, a.top, summary=summary)
    print(json.dumps(report, indent=2) if a.json else markdown(report), end="" if not a.json else "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
