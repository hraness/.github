#!/usr/bin/env python3
"""Check a repository's GitHub Actions workflows against the Hraness CI cost rules.

usage: scripts/ci-cost-lint.py [DIR] [--repo OWNER/NAME] [--visibility auto|private|public] [--json]

Reads DIR/.github/workflows (default: the current directory), or the default
branch of --repo through `gh api`. Rules (see the hraness-ci block in AGENTS.md):

  native-runner   a macOS or Windows runner (runs-on or matrix value) in a job
                  without a `# cost-lint: native-surface` comment
  no-concurrency  a workflow with no `concurrency` (workflow_call-only
                  workflows are exempt: the caller owns concurrency)
  push-cancel     a workflow triggered by push with `cancel-in-progress: true`;
                  use `${{ github.event_name == 'pull_request' }}` so a later
                  run never cancels one on main
  pr-cache-save   a pull_request workflow step that can save a cache:
                  actions/cache (not /restore), actions/cache/save without a
                  main-only `if`, Swatinem/rust-cache without `save-if`,
                  setup-node/setup-python `cache:`, setup-uv caching without
                  `save-cache`
  no-timeout      a job without `timeout-minutes`

Findings are errors in private repositories (billed minutes) and warnings in
public ones. The exit status is 1 only when the repository is private and has
at least one finding; 2 on usage or input errors.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

MARKER = "cost-lint: native-surface"
NATIVE = re.compile(r"^\s*(macos|windows)\b", re.IGNORECASE)
MAIN_ONLY = re.compile(r"refs/heads/main|github\.ref_name\s*==\s*'main'|event_name\s*(==\s*'(push|schedule|workflow_dispatch)'|!=\s*'pull_request')")


@dataclass
class Finding:
    file: str
    job: str | None
    rule: str
    message: str
    severity: str = "warning"


def gh() -> str:
    return os.environ.get("GH") or shutil.which("gh") or "gh"


def run(cmd: list[str], stdin: str | None = None) -> str:
    result = subprocess.run(cmd, input=stdin, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:4])} failed: {result.stderr.strip()[:400]}")
    return result.stdout


def load_yaml(text: str) -> object:
    """Parse YAML with PyYAML when installed, otherwise with `yq` (present on GitHub runners)."""
    try:
        import yaml  # type: ignore
    except ImportError:
        yq = shutil.which("yq")
        if not yq:
            raise RuntimeError("needs PyYAML or yq to parse workflows")
        return json.loads(run([yq, "-o=json", "."], stdin=text) or "null")
    return yaml.safe_load(text)


def triggers(workflow: dict) -> set[str]:
    # PyYAML (YAML 1.1) reads the bare key `on` as True.
    on = workflow.get("on", workflow.get(True))
    if isinstance(on, str):
        return {on}
    if isinstance(on, list):
        return {str(x) for x in on}
    if isinstance(on, dict):
        return {str(k) for k in on}
    return set()


def strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in strings(v)]
    return []


def job_texts(text: str) -> dict[str, str]:
    """Raw text of each job under the top-level `jobs:` key, for comment markers."""
    lines = text.splitlines()
    out: dict[str, list[str]] = {}
    in_jobs = False
    indent = None
    current = None
    for line in lines:
        if re.match(r"^jobs:\s*(#.*)?$", line):
            in_jobs = True
            continue
        if not in_jobs:
            continue
        if line.strip() and not line[0].isspace() and not line.lstrip().startswith("#"):
            break
        m = re.match(r"^(\s+)([A-Za-z0-9_-]+|'[^']+'|\"[^\"]+\"):\s*(#.*)?$", line)
        if m and (indent is None or len(m.group(1)) == indent):
            indent = len(m.group(1))
            current = m.group(2).strip("'\"")
            out[current] = [line]
            continue
        if current is not None:
            out[current].append(line)
    return {k: "\n".join(v) for k, v in out.items()}


def cancel_is_true(concurrency: object) -> bool:
    if not isinstance(concurrency, dict):
        return False
    value = concurrency.get("cancel-in-progress")
    return value is True or (isinstance(value, str) and value.strip().lower() == "true")


def lint_workflow(name: str, text: str) -> list[Finding]:
    try:
        workflow = load_yaml(text)
    except Exception as error:  # noqa: BLE001 - report any parser failure as a finding
        return [Finding(name, None, "parse", f"cannot parse workflow: {error}")]
    if not isinstance(workflow, dict):
        return [Finding(name, None, "parse", "workflow is not a mapping")]
    on = triggers(workflow)
    jobs = workflow.get("jobs") or {}
    if not isinstance(jobs, dict):
        jobs = {}
    raw = job_texts(text)
    findings: list[Finding] = []

    workflow_concurrency = workflow.get("concurrency")
    reusable_only = on == {"workflow_call"}
    if workflow_concurrency is None and not reusable_only:
        if not jobs or not all(isinstance(j, dict) and j.get("concurrency") is not None for j in jobs.values()):
            findings.append(Finding(name, None, "no-concurrency", "workflow has no concurrency group, so superseded runs keep billing"))
    if "push" in on:
        if cancel_is_true(workflow_concurrency):
            findings.append(Finding(name, None, "push-cancel", "push-triggered workflow cancels in progress unconditionally; use cancel-in-progress: ${{ github.event_name == 'pull_request' }}"))
        for job_id, job in jobs.items():
            if isinstance(job, dict) and cancel_is_true(job.get("concurrency")):
                findings.append(Finding(name, job_id, "push-cancel", "job concurrency cancels in progress unconditionally in a push-triggered workflow"))

    on_pr = bool(on & {"pull_request", "pull_request_target"})
    for job_id, job in jobs.items():
        if not isinstance(job, dict):
            continue
        runners = strings(job.get("runs-on")) + strings((job.get("strategy") or {}).get("matrix") if isinstance(job.get("strategy"), dict) else None)
        native = sorted({s.strip() for s in runners if NATIVE.match(s)})
        if native and MARKER not in raw.get(job_id, ""):
            findings.append(Finding(name, job_id, "native-runner", f"{', '.join(native)} runner without a `# {MARKER}` comment; private-repo macOS minutes cost 10x Linux and Windows 1.7x"))
        if "uses" not in job and "timeout-minutes" not in job:
            findings.append(Finding(name, job_id, "no-timeout", "job has no timeout-minutes (the default is 360)"))
        if not on_pr:
            continue
        job_if = str(job.get("if", ""))
        for step in job.get("steps") or []:
            if not isinstance(step, dict):
                continue
            uses = str(step.get("uses", ""))
            action = uses.split("@", 1)[0].lower()
            with_ = step.get("with") if isinstance(step.get("with"), dict) else {}
            guard = f"{job_if} {step.get('if', '')}"
            label = step.get("name") or uses
            problem = None
            if action == "actions/cache":
                problem = "actions/cache also saves on pull requests; use actions/cache/restore on pull requests and actions/cache/save on main"
            elif action == "actions/cache/save" and not MAIN_ONLY.search(guard):
                problem = "actions/cache/save is reachable on pull_request; guard it with if: github.ref == 'refs/heads/main'"
            elif action == "swatinem/rust-cache" and "save-if" not in with_:
                problem = "rust-cache saves on pull requests; set save-if: ${{ github.ref == 'refs/heads/main' }}"
            elif action in ("actions/setup-node", "actions/setup-python") and with_.get("cache"):
                problem = f"{action} `cache:` saves on pull requests; use an actions/cache/restore + main-only save pair"
            elif action == "astral-sh/setup-uv" and str(with_.get("enable-cache", "")).lower() == "true" and "save-cache" not in with_:
                problem = "setup-uv saves its cache on pull requests; set save-cache: ${{ github.ref == 'refs/heads/main' }}"
            if problem:
                findings.append(Finding(name, job_id, "pr-cache-save", f"{label}: {problem}"))
    return findings


def workflows_from_dir(root: Path) -> dict[str, str]:
    directory = root / ".github" / "workflows"
    if not directory.is_dir():
        return {}
    return {f".github/workflows/{p.name}": p.read_text() for p in sorted(directory.iterdir()) if p.suffix in (".yml", ".yaml") and p.is_file()}


def workflows_from_repo(repo: str) -> dict[str, str]:
    try:
        listing = json.loads(run([gh(), "api", f"repos/{repo}/contents/.github/workflows"]))
    except RuntimeError as error:
        if "404" in str(error) or "Not Found" in str(error):
            return {}
        raise
    out = {}
    for entry in sorted(listing, key=lambda e: e["name"]):
        if entry.get("type") == "file" and entry["name"].endswith((".yml", ".yaml")):
            blob = json.loads(run([gh(), "api", f"repos/{repo}/contents/{entry['path']}"]))
            out[entry["path"]] = base64.b64decode(blob["content"]).decode()
    return out


def visibility_of(repo: str | None, root: Path) -> str:
    try:
        if repo:
            return run([gh(), "api", f"repos/{repo}", "--jq", ".visibility"]).strip() or "unknown"
        result = subprocess.run([gh(), "repo", "view", "--json", "visibility", "--jq", ".visibility"], cwd=root, capture_output=True, text=True)
        if result.returncode != 0:
            return "unknown"
        return result.stdout.strip().lower() or "unknown"
    except (RuntimeError, OSError):
        return "unknown"


def lint(workflows: dict[str, str], visibility: str) -> list[Finding]:
    severity = "error" if visibility == "private" else "warning"
    findings = [f for name, text in workflows.items() for f in lint_workflow(name, text)]
    for f in findings:
        f.severity = severity
    return findings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("dir", nargs="?", default=".")
    ap.add_argument("--repo", help="OWNER/NAME; read workflows from GitHub instead of DIR")
    ap.add_argument("--visibility", choices=["auto", "private", "public"], default="auto")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    root = Path(a.dir)
    try:
        workflows = workflows_from_repo(a.repo) if a.repo else workflows_from_dir(root)
        visibility = a.visibility if a.visibility != "auto" else visibility_of(a.repo, root)
        findings = lint(workflows, visibility)
    except RuntimeError as error:
        print(f"ci-cost-lint: {error}", file=sys.stderr)
        return 2
    target = a.repo or str(root)
    if a.json:
        print(json.dumps({"target": target, "visibility": visibility, "workflows": len(workflows), "findings": [asdict(f) for f in findings]}, indent=2))
    else:
        for f in findings:
            where = f"{f.file}:{f.job}" if f.job else f.file
            print(f"{f.severity}: {where}: {f.rule}: {f.message}")
        print(f"ci-cost-lint: {target} ({visibility}): {len(workflows)} workflow(s), {len(findings)} finding(s)")
    return 1 if visibility == "private" and findings else 0


if __name__ == "__main__":
    sys.exit(main())
