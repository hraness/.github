#!/usr/bin/env python3
"""Report repositories whose AGENTS.md blocks differ from the canonical hraness-* blocks.

usage: scripts/sync-agent-blocks.py --check [--org ORG] [--visibility public|private|all]
                                    [--repo OWNER/NAME ...] [--path DIR ...]
                                    [--canonical AGENTS.md] [--json]

The canonical text is every `<!-- hraness-<name>:start -->` ... `:end -->` block
in this repository's AGENTS.md. Each target repository's AGENTS.md is compared
block by block, following the applicability rules in that file:

  hraness-delivery, hraness-public-copy   every repository
  hraness-ci        every repository with files in .github/workflows
  hraness-releases  every repository that has published a GitHub Release
  hraness-launch    every repository that carries hraness-articles
  hraness-articles  (and launch otherwise) checked only when present

A repository keeps its own lines for a block after a `<!-- hraness-<name>:additions -->`
line inside the block; only the text above that line is compared. Lines are
compared after trimming trailing whitespace and surrounding blank lines.

Targets: --path reads local checkouts (releases are then checked only when the
block is present); --repo and --org read default branches through `gh api`.
Archived repositories, forks and this repository are skipped. --check is
report-only: it never writes to a repository. Exit status 1 when any target has
a drifted or missing block, 2 on usage or input errors.
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
from pathlib import Path

BLOCK = re.compile(r"<!-- (hraness-[a-z0-9-]+):start -->\n(.*?)<!-- \1:end -->", re.DOTALL)
ALWAYS = ("hraness-delivery", "hraness-public-copy")
SELF = ".github"


def normalize(text: str) -> str:
    lines = [line.rstrip() for line in text.splitlines()]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def blocks(text: str) -> dict[str, str]:
    out = {}
    for match in BLOCK.finditer(text):
        name, body = match.group(1), match.group(2)
        body = re.split(rf"^<!-- {re.escape(name)}:additions -->\s*$", body, maxsplit=1, flags=re.MULTILINE)[0]
        out[name] = normalize(body)
    return out


def required(name: str, present: dict[str, str], facts: dict[str, bool | None]) -> bool | None:
    """True: the block must be present. False: not applicable. None: check only when present."""
    if name in ALWAYS:
        return True
    if name == "hraness-ci":
        return facts.get("workflows")
    if name == "hraness-releases":
        return True if facts.get("releases") else None
    if name == "hraness-launch":
        return True if "hraness-articles" in present else None
    return None


def compare(canonical: dict[str, str], agents_md: str | None, facts: dict[str, bool | None]) -> dict[str, str]:
    """Status per canonical block: ok, drift, missing, or n/a."""
    if agents_md is None:
        return {name: ("missing" if required(name, {}, facts) else "n/a") for name in canonical}
    present = blocks(agents_md)
    status = {}
    for name, text in canonical.items():
        need = required(name, present, facts)
        if name in present:
            status[name] = "ok" if present[name] == text else "drift"
        else:
            status[name] = "missing" if need else "n/a"
    return status


def gh() -> str:
    return os.environ.get("GH") or shutil.which("gh") or "gh"


def gh_api(path: str, paginate: bool = False) -> object | None:
    cmd = [gh(), "api", path] + (["--paginate", "--slurp"] if paginate else [])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        if "404" in result.stderr or "Not Found" in result.stderr:
            return None
        raise RuntimeError(f"gh api {path} failed: {result.stderr.strip()[:300]}")
    data = json.loads(result.stdout) if result.stdout.strip() else None
    return [item for page in data for item in page] if paginate and data is not None else data


def remote_target(repo: str) -> tuple[str | None, dict[str, bool | None]]:
    blob = gh_api(f"repos/{repo}/contents/AGENTS.md")
    text = base64.b64decode(blob["content"]).decode() if isinstance(blob, dict) and blob.get("content") else None
    workflows = gh_api(f"repos/{repo}/contents/.github/workflows")
    has_workflows = bool(workflows) and any(str(e.get("name", "")).endswith((".yml", ".yaml")) for e in workflows)
    releases = gh_api(f"repos/{repo}/releases?per_page=1")
    return text, {"workflows": has_workflows, "releases": bool(releases)}


def local_target(root: Path) -> tuple[str | None, dict[str, bool | None]]:
    agents = root / "AGENTS.md"
    workflows = root / ".github" / "workflows"
    has_workflows = workflows.is_dir() and any(p.suffix in (".yml", ".yaml") for p in workflows.iterdir())
    return (agents.read_text() if agents.is_file() else None), {"workflows": has_workflows, "releases": None}


def org_repos(org: str, visibility: str) -> list[str]:
    kind = {"public": "public", "private": "private", "all": "all"}[visibility]
    repos = gh_api(f"orgs/{org}/repos?type={kind}&per_page=100", paginate=True) or []
    return sorted(r["full_name"] for r in repos if not r.get("archived") and not r.get("fork") and r["name"] != SELF)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", required=True, help="report drift without writing (the only mode)")
    ap.add_argument("--org")
    ap.add_argument("--visibility", choices=["public", "private", "all"], default="public")
    ap.add_argument("--repo", action="append", default=[])
    ap.add_argument("--path", action="append", default=[])
    ap.add_argument("--canonical", default=str(Path(__file__).resolve().parent.parent / "AGENTS.md"))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    canonical = blocks(Path(a.canonical).read_text())
    if not canonical:
        print(f"sync-agent-blocks: no hraness-* blocks in {a.canonical}", file=sys.stderr)
        return 2
    targets: list[tuple[str, str]] = [("path", p) for p in a.path] + [("repo", r) for r in a.repo]
    try:
        if a.org:
            targets += [("repo", r) for r in org_repos(a.org, a.visibility)]
        if not targets:
            ap.error("give --org, --repo or --path")
        results = {}
        for kind, target in targets:
            text, facts = local_target(Path(target)) if kind == "path" else remote_target(target)
            results[target] = {"agents_md": text is not None, "blocks": compare(canonical, text, facts)}
    except RuntimeError as error:
        print(f"sync-agent-blocks: {error}", file=sys.stderr)
        return 2

    drifted = {t: r for t, r in results.items() if any(s in ("drift", "missing") for s in r["blocks"].values())}
    if a.json:
        print(json.dumps({"canonical": sorted(canonical), "checked": len(results), "drifted": sorted(drifted), "results": results}, indent=2))
    else:
        names = sorted(canonical)
        print(f"# Agent block drift: {len(drifted)} of {len(results)} repositories\n")
        if drifted:
            print("| repository | " + " | ".join(n.removeprefix("hraness-") for n in names) + " |")
            print("|---|" + "---|" * len(names))
            for target, result in sorted(drifted.items()):
                note = "" if result["agents_md"] else " (no AGENTS.md)"
                print(f"| {target}{note} | " + " | ".join(result["blocks"][n] for n in names) + " |")
            print("\nCopy each drifted or missing block verbatim from hraness/.github AGENTS.md; keep repository-specific lines after a `<!-- hraness-<name>:additions -->` line.")
    return 1 if drifted else 0


if __name__ == "__main__":
    sys.exit(main())
