#!/usr/bin/env python3
"""Register the canonical browser policy in local agent instruction files."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

START = b"<!-- browser-automation:start -->"
END = b"<!-- browser-automation:end -->"


def bounds(data: bytes) -> tuple[int, int] | None:
    if not data.count(START) and not data.count(END):
        return None
    if data.count(START) != 1 or data.count(END) != 1:
        raise ValueError("missing or duplicate browser policy marker")
    start, end = data.index(START), data.index(END)
    if end < start:
        raise ValueError("reversed browser policy markers")
    return start, end + len(END)


def snapshot(path: Path) -> tuple[bytes, int, tuple[int, ...]] | None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"instruction file is not a regular file: {path}")
    data = path.read_bytes()
    identity = (info.st_dev, info.st_ino, info.st_mtime_ns, info.st_ctime_ns, info.st_size)
    return data, stat.S_IMODE(info.st_mode), identity


def targets(home: Path, fixture: bool = False) -> list[tuple[str, Path]]:
    env = {} if fixture else os.environ
    def root(name: str, fallback: Path) -> Path:
        configured = env.get(name)
        path = Path(configured) if configured else fallback.absolute()
        if not path.is_absolute():
            raise ValueError(f"{name} must be an absolute directory path")
        return path

    codex = root("CODEX_HOME", home / ".codex")
    claude = root("CLAUDE_CONFIG_DIR", home / ".claude")
    config = root("XDG_CONFIG_HOME", home / ".config")
    result = [("codex", codex / "AGENTS.md"), ("claude", claude / "CLAUDE.md"),
              ("devin", config / "devin" / "AGENTS.md")]
    override = codex / "AGENTS.override.md"
    current = snapshot(override)
    if current is not None and current[0].strip():
        result.append(("codex-override", override))
    # Resolve directory aliases while leaving the final file for snapshot's
    # explicit symlink rejection. Pin these parents for planning and writing.
    result = [(agent, path.parent.resolve() / path.name) for agent, path in result]
    if len({path for _, path in result}) != len(result):
        raise ValueError("agent instruction targets overlap")
    return result


def plan(policy: bytes, selected: list[tuple[str, Path]]) -> list[dict]:
    result = []
    for agent, path in selected:
        before = snapshot(path)
        data = before[0] if before else b""
        span = bounds(data)
        if span:
            after = data[:span[0]] + policy + data[span[1]:]
        else:
            separator = b"" if not data or data.endswith(b"\n\n") else (b"\n" if data.endswith(b"\n") else b"\n\n")
            after = data + separator + policy + b"\n"
        result.append(dict(agent=agent, path=path, before=before, after=after,
                           status="ok" if data == after else "drift"))
    return result


def unchanged(rows: list[dict]) -> None:
    for row in rows:
        if snapshot(row["path"]) != row["before"]:
            raise ValueError(f"instruction file changed concurrently: {row['path']}")


def write(rows: list[dict], backup_dir: Path) -> None:
    unchanged(rows)  # Validate every target before the first mutation.
    changed = [row for row in rows if row["status"] != "ok"]
    if not changed:
        return
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix="browser-policy-", dir=backup_dir))
    for row in changed:
        if row["before"] is not None:
            saved = backup / (row["agent"] + ".md")
            saved.write_bytes(row["before"][0])
            saved.chmod(0o600)
            row["backup"] = str(saved)
        else:
            row["backup"] = None
    unchanged(rows)
    for row in changed:
        path = row["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".browser-policy-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as output:
                output.write(row["after"])
                output.flush()
                os.fsync(output.fileno())
                os.fchmod(output.fileno(), row["before"][1] if row["before"] else 0o600)
            unchanged([row])
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        row["status"] = "updated"


def target_report(rows: list[dict]) -> list[dict]:
    return [{k: str(v) if k == "path" else v for k, v in row.items()
             if k in ("agent", "path", "status", "backup")} for row in rows]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check", action="store_true", help="report drift (default)")
    modes.add_argument("--dry-run", action="store_true")
    modes.add_argument("--write", action="store_true")
    parser.add_argument("--home", type=Path, help="fixture home; ignore agent environment overrides")
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.write and args.backup_dir is None:
        parser.error("--write requires --backup-dir")
    rows: list[dict] = []
    try:
        canonical = (Path(__file__).resolve().parent.parent / "AGENTS.md").read_bytes()
        span = bounds(canonical)
        if span is None:
            raise ValueError("canonical browser policy markers are missing")
        policy = canonical[span[0]:span[1]]
        rows = plan(policy, targets(args.home or Path.home(), args.home is not None))
        if args.write:
            write(rows, args.backup_dir)
        report = dict(policy_sha256=hashlib.sha256(policy).hexdigest(),
                      targets=target_report(rows))
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(f"Policy SHA-256: {report['policy_sha256']}")
            for row in report["targets"]:
                print(f"{row['agent']}: {row['status']} {row['path']}")
        return 1 if not (args.write or args.dry_run) and any(r["status"] == "drift" for r in rows) else 0
    except (OSError, ValueError) as error:
        report = {"error": str(error), "targets": target_report(rows)}
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(f"register-browser-policy: {error}")
            for row in report["targets"]:
                print(f"{row['agent']}: {row['status']} {row['path']} backup={row.get('backup')}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
