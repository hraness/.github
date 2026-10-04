#!/usr/bin/env python3
"""Check or install the shared dependency audit workflow in organization repositories.

usage: scripts/sync-dependency-audit.py (--check | --apply) [--org ORG] [--visibility public|private|all]
                                        [--repo OWNER/NAME ...] [--include-forks] [--action-sha SHA] [--json]

Every repository that tracks a lockfile listed in actions/dependency-audit/lockfiles.json
should carry .github/workflows/dependency-audit.yml exactly as templates/dependency-audit.yml
renders it, with the action pinned to the newest commit of this repository's main branch
that changed actions/dependency-audit (or --action-sha). A newer actions/checkout commit
pinned with its version comment, as Dependabot updates it, still counts as current.

Each target is one of:

  ok              the workflow matches the rendered template
  outdated        the workflow matches except for an older action commit
  drifted         the workflow exists but differs from the template
  missing         the repository tracks a lockfile but has no workflow
  not-applicable  the repository tracks no supported lockfile

--check is report-only. It also shows the latest audit run on the default branch and
the open tracking issue. Exit status 1 when any target is outdated, drifted or missing,
2 on usage or input errors.

--apply opens one pull request per outdated, drifted or missing target with the rendered
workflow and enables auto-merge; each repository's own required checks still gate the
merge. It never pushes to a default branch and reuses an open pull request from an
earlier run.

Targets: --repo, or --org discovery, which skips archived repositories and, unless
--include-forks is given, forks.
"""
from __future__ import annotations

import argparse
import base64
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "templates" / "dependency-audit.yml"
LOCKFILES = ROOT / "actions" / "dependency-audit" / "lockfiles.json"
WORKFLOW = ".github/workflows/dependency-audit.yml"
ACTION = "hraness/.github/actions/dependency-audit"
PLACEHOLDER = "__ACTION_SHA__"
USES = re.compile(r"^(\s*- uses: hraness/\.github/actions/dependency-audit@)([0-9a-f]{40})( # main)$", re.MULTILINE)
CHECKOUT = re.compile(r"^(\s*- uses: actions/checkout@)[0-9a-f]{40} # v\d+(?:\.\d+)*$", re.MULTILINE)
SHA = re.compile(r"^[0-9a-f]{40}$")
FAILING = ("outdated", "drifted", "missing")


def gh() -> str:
    return os.environ.get("GH") or shutil.which("gh") or "gh"


def run(cmd: list[str], stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, input=stdin, capture_output=True, text=True)


def gh_api(path: str, paginate: bool = False, method: str = "GET", body: dict | None = None) -> object | None:
    cmd = [gh(), "api", path, "--method", method] + (["--paginate", "--slurp"] if paginate else [])
    if body is not None:
        cmd += ["--input", "-"]
    result = run(cmd, json.dumps(body) if body is not None else None)
    if result.returncode != 0:
        if "HTTP 404" in result.stderr or "Not Found" in result.stderr:
            return None
        raise RuntimeError(f"gh api {method} {path} failed: {result.stderr.strip()[:300]}")
    data = json.loads(result.stdout) if result.stdout.strip() else None
    return [item for page in data for item in page] if paginate and data is not None else data


def lockfile_globs() -> list[str]:
    return json.loads(LOCKFILES.read_text())


def is_lockfile(path: str, globs: list[str]) -> bool:
    parts = path.split("/")
    return "node_modules" not in parts and any(fnmatch.fnmatchcase(parts[-1], glob) for glob in globs)


def render(sha: str) -> str:
    if not SHA.match(sha):
        raise ValueError(f"action commit must be a full 40-character SHA, not {sha!r}")
    template = TEMPLATE.read_text()
    if template.count(PLACEHOLDER) != 1:
        raise ValueError(f"{TEMPLATE} must contain {PLACEHOLDER} exactly once")
    return template.replace(PLACEHOLDER, sha)


def classify(current: str | None, expected: str, applicable: bool) -> str:
    if not applicable:
        return "not-applicable"
    if current is None:
        return "missing"
    current, expected = (CHECKOUT.sub(r"\1PINNED", text) for text in (current, expected))
    if current == expected:
        return "ok"
    if USES.sub(r"\1" + "0" * 40 + r"\3", current) == USES.sub(r"\1" + "0" * 40 + r"\3", expected):
        return "outdated"
    return "drifted"


def action_sha() -> str:
    commits = gh_api(f"repos/hraness/.github/commits?sha=main&path={quote('actions/dependency-audit')}&per_page=1")
    if not commits:
        raise RuntimeError("found no commit of actions/dependency-audit on hraness/.github main")
    return commits[0]["sha"]


def org_repos(org: str, visibility: str, include_forks: bool) -> list[dict]:
    repos = gh_api(f"orgs/{org}/repos?type={visibility}&per_page=100", paginate=True) or []
    return sorted((r for r in repos if not r.get("archived") and (include_forks or not r.get("fork"))), key=lambda r: r["full_name"])


def repo_info(name: str) -> dict:
    info = gh_api(f"repos/{name}")
    if not isinstance(info, dict):
        raise RuntimeError(f"repository {name} was not found")
    return info


def inspect(repo: dict, expected: str, globs: list[str]) -> dict:
    name, branch = repo["full_name"], repo.get("default_branch") or "main"
    tree = gh_api(f"repos/{name}/git/trees/{quote(branch)}?recursive=1") or {}
    paths = [item["path"] for item in tree.get("tree", []) if item.get("type") == "blob"]
    lockfiles = sorted(path for path in paths if is_lockfile(path, globs))
    blob = gh_api(f"repos/{name}/contents/{WORKFLOW}?ref={quote(branch)}")
    current = base64.b64decode(blob["content"]).decode() if isinstance(blob, dict) and blob.get("content") else None
    status = classify(current, expected, bool(lockfiles))
    entry = {"repo": name, "branch": branch, "status": status, "lockfiles": len(lockfiles), "truncated": bool(tree.get("truncated")),
             "run": None, "issue": None}
    if current is not None:
        runs = gh_api(f"repos/{name}/actions/workflows/dependency-audit.yml/runs?branch={quote(branch)}&per_page=1") or {}
        latest = (runs.get("workflow_runs") or [None])[0]
        if latest:
            entry["run"] = {"conclusion": latest.get("conclusion") or latest.get("status"), "event": latest.get("event"),
                            "url": latest.get("html_url"), "created_at": latest.get("created_at")}
        issues = gh_api(f"repos/{name}/issues?state=open&labels=dependency-audit&per_page=5") or []
        issue = next((i for i in issues if not i.get("pull_request") and str(i.get("title", "")).startswith("Dependency audit:")), None)
        if issue:
            entry["issue"] = {"number": issue["number"], "title": issue["title"], "url": issue["html_url"]}
    return entry


PR_TITLE = "Run the shared dependency audit"
PR_BODY = """## Summary

- Adds or updates `.github/workflows/dependency-audit.yml` from `templates/dependency-audit.yml` in hraness/.github, pinned to action commit `{sha}`.
- The audit scans every tracked lockfile with a pinned OSV-Scanner on pull requests that change a lockfile, on pushes to `main`, daily, and on demand.
- A pull request fails the audit only when it adds a known vulnerability. The run on `main` keeps one `dependency-audit` issue current with every known vulnerability and closes it when none remain.
- The check is advisory: do not add it to required checks.

#### Test plan

- [ ] The audit runs on this pull request and its summary lists the scanned lockfiles
- [ ] Required CI
"""


def open_pull_request(entry: dict, content: str, sha: str) -> str:
    name, base = entry["repo"], entry["branch"]
    branch = f"hraness/dependency-audit-{sha[:12]}"
    existing = gh_api(f"repos/{name}/pulls?state=open&head={quote(name.split('/')[0] + ':' + branch)}") or []
    if existing:
        return existing[0]["html_url"]
    head = gh_api(f"repos/{name}/git/ref/heads/{quote(base)}")
    if gh_api(f"repos/{name}/git/ref/heads/{quote(branch)}") is None:
        gh_api(f"repos/{name}/git/refs", method="POST", body={"ref": f"refs/heads/{branch}", "sha": head["object"]["sha"]})
    current = gh_api(f"repos/{name}/contents/{WORKFLOW}?ref={quote(branch)}")
    body = {"message": f"{PR_TITLE}\n\nInstall the dependency audit workflow from hraness/.github at {sha}.",
            "content": base64.b64encode(content.encode()).decode(), "branch": branch}
    if isinstance(current, dict) and current.get("sha"):
        body["sha"] = current["sha"]
    gh_api(f"repos/{name}/contents/{WORKFLOW}", method="PUT", body=body)
    pull = gh_api(f"repos/{name}/pulls", method="POST",
                  body={"title": PR_TITLE, "head": branch, "base": base, "body": PR_BODY.format(sha=sha)})
    url = pull["html_url"]
    merge = run([gh(), "pr", "merge", "--auto", "--squash", url])
    if merge.returncode != 0:
        print(f"sync-dependency-audit: auto-merge was not enabled for {url}: {merge.stderr.strip()[:200]}", file=sys.stderr)
    return url


def describe(entry: dict) -> str:
    run_text = "no run yet"
    if entry["run"]:
        run_text = f"{entry['run']['conclusion']} ({entry['run']['event']})"
    issue = f"issue #{entry['issue']['number']}" if entry["issue"] else "no open issue"
    return f"{entry['status']:<14} {entry['repo']}  lockfiles={entry['lockfiles']}  latest run: {run_text}  {issue}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="report coverage and status without writing")
    mode.add_argument("--apply", action="store_true", help="open a pull request for every outdated, drifted or missing target")
    ap.add_argument("--org")
    ap.add_argument("--visibility", choices=["public", "private", "all"], default="public")
    ap.add_argument("--repo", action="append", default=[])
    ap.add_argument("--include-forks", action="store_true", help="include active forks in organization discovery")
    ap.add_argument("--action-sha", help="pin this commit instead of the newest commit that changed the action")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if not a.org and not a.repo:
        ap.error("give --org or --repo")
    try:
        sha = a.action_sha or action_sha()
        expected = render(sha)
        globs = lockfile_globs()
        repos = org_repos(a.org, a.visibility, a.include_forks) if a.org else []
        repos += [repo_info(name) for name in a.repo if name not in {r["full_name"] for r in repos}]
        results = [inspect(repo, expected, globs) for repo in repos]
        if a.apply:
            for entry in results:
                if entry["status"] in FAILING:
                    entry["pull_request"] = open_pull_request(entry, expected, sha)
    except (RuntimeError, ValueError) as error:
        print(f"sync-dependency-audit: {error}", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps({"action_sha": sha, "results": results}, indent=2))
    else:
        print(f"Dependency audit coverage, action {ACTION}@{sha[:12]}\n")
        for entry in results:
            print(describe(entry) + (f"\n               pull request: {entry['pull_request']}" if entry.get("pull_request") else ""))
        counts = {status: sum(1 for e in results if e["status"] == status) for status in ("ok", *FAILING, "not-applicable")}
        print("\n" + ", ".join(f"{count} {status}" for status, count in counts.items()))
    return 1 if a.check and any(entry["status"] in FAILING for entry in results) else 0


if __name__ == "__main__":
    sys.exit(main())
