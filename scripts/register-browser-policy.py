#!/usr/bin/env python3
"""Register the canonical browser policy in global or repository agent instructions."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile

START = b"<!-- browser-automation:start -->"
END = b"<!-- browser-automation:end -->"
REPOSITORY_FILES = ("AGENTS.md", "CLAUDE.md", "AGENTS.override.md")
HOSTED_INSTRUCTION_LIMIT = 16 * 1024


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


def repository_root(path: Path) -> Path:
    """Require Git's actual worktree root, not a nested folder or a .git impostor."""
    try:
        root = path.resolve(strict=True)
        marker = (root / ".git").lstat()
    except (OSError, RuntimeError) as error:
        raise ValueError(f"not a Git repository root: {path}") from error
    if not root.is_dir() or not (stat.S_ISREG(marker.st_mode) or stat.S_ISDIR(marker.st_mode)):
        raise ValueError(f"not a Git repository root: {path}")
    # Ambient Git overrides must not turn a non-repository into a valid target.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    result = subprocess.run(["git", "--no-optional-locks", "-C", str(root),
                             "rev-parse", "--show-toplevel"], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise ValueError(f"not a Git repository root: {path}")
    try:
        actual = Path(os.fsdecode(result.stdout.removesuffix(b"\n"))).resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ValueError(f"not a Git repository root: {path}") from error
    if actual != root:
        raise ValueError(f"not a Git repository root: {path}")
    return root


def repository_identity(root: Path) -> tuple:
    """Pin the root and Git marker, allowing ordinary changes inside .git dirs."""
    info = root.lstat()
    marker = (root / ".git").lstat()
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError(f"repository root changed concurrently: {root}")
    if stat.S_ISREG(marker.st_mode):
        evidence = ("file", snapshot(root / ".git"))
    elif stat.S_ISDIR(marker.st_mode):
        evidence = ("directory", marker.st_dev, marker.st_ino)
    else:
        raise ValueError(f"repository Git marker changed concurrently: {root}")
    return (info.st_dev, info.st_ino), evidence


def alias_snapshot(path: Path) -> tuple | None:
    """Pin symlink identities and their text without following their target."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    identity = (info.st_dev, info.st_ino, info.st_mode, info.st_mtime_ns,
                info.st_ctime_ns, info.st_size)
    return identity, os.readlink(path) if stat.S_ISLNK(info.st_mode) else None


def repository_instruction(root: Path, name: str) -> tuple[Path, tuple | None, list]:
    """Follow only existing aliases among the three root instruction filenames."""
    current = root / name
    seen = set()
    guards = []
    while True:
        if current in seen:
            raise ValueError(f"cyclic repository instruction alias: {root / name}")
        seen.add(current)
        try:
            info = current.lstat()
        except FileNotFoundError as error:
            if guards:
                raise ValueError(f"dangling repository instruction alias: {root / name}") from error
            return current, None, guards
        if not stat.S_ISLNK(info.st_mode):
            if stat.S_ISREG(info.st_mode) and info.st_nlink > 1:
                raise ValueError(f"hard-linked repository instruction files are unsupported: {current}; use a root instruction symlink")
            return current, snapshot(current), guards
        saved = alias_snapshot(current)
        expected = (info.st_dev, info.st_ino, info.st_mode, info.st_mtime_ns,
                    info.st_ctime_ns, info.st_size)
        if saved is None or saved[0] != expected:
            raise ValueError(f"instruction alias changed concurrently: {current}")
        guards.append((current, saved))
        target = Path(saved[1])
        current = Path(os.path.abspath(target if target.is_absolute() else current.parent / target))
        if current.parent != root or current.name not in REPOSITORY_FILES:
            raise ValueError(f"repository instruction alias leaves root instruction files: {root / name}")


def active_agents_import(data: bytes) -> bool:
    """Find a standalone Claude import outside fenced/indented code and comments."""
    fence = None
    comment = False
    for line in data.splitlines():
        if fence is not None:
            character, length = fence
            if re.fullmatch(b" {0,3}" + re.escape(character) + b"{" + str(length).encode() + b",}[ \t]*", line):
                fence = None
            continue
        # Tabs reach a Markdown code indentation even after up to three spaces.
        if not comment and re.match(b"(?: {4}| {0,3}\t)", line):
            continue
        visible = bytearray()
        cursor = 0
        while cursor < len(line):
            if comment:
                end = line.find(b"-->", cursor)
                if end < 0:
                    break
                cursor, comment = end + 3, False
            else:
                start = line.find(b"<!--", cursor)
                if start < 0:
                    visible.extend(line[cursor:])
                    break
                visible.extend(line[cursor:start])
                cursor, comment = start + 4, True
        opening = re.match(b"^ {0,3}(`{3,}|~{3,})(.*)$", bytes(visible))
        if opening and not (opening[1].startswith(b"`") and b"`" in opening[2]):
            fence = opening[1][:1], len(opening[1])
        elif not comment and bytes(visible) == line and line.strip(b" \t") in (b"@AGENTS.md", b"@./AGENTS.md"):
            return True
    return False


def early_policy(policy: bytes, data: bytes) -> bytes:
    """Move the managed block to byte zero while retaining every unmanaged byte."""
    span = bounds(data)
    if span is not None:
        remainder = data[:span[0]] + data[span[1]:]
        return policy + (b"\n\n" if span[0] else b"") + remainder
    return policy + (b"\n\n" + data if data else b"\n")


def repository_plan(policy: bytes, repositories: list[Path]) -> list[dict]:
    if len(policy) > HOSTED_INSTRUCTION_LIMIT:
        raise ValueError("canonical browser policy exceeds the hosted-agent 16 KiB instruction limit")
    roots = [repository_root(path) for path in repositories]
    for index, root in enumerate(roots):
        if any(root == other or root in other.parents or other in root.parents for other in roots[:index]):
            raise ValueError("repository instruction targets overlap")
    rows = []
    for index, root in enumerate(roots, 1):
        identity = repository_identity(root)
        records = {}
        for name in REPOSITORY_FILES:
            path, before, guards = repository_instruction(root, name)
            data = before[0] if before else b""
            span = bounds(data)  # Imported and inactive files must also have valid markers.
            if path in records and records[path]["before"] != before:
                raise ValueError(f"instruction file changed concurrently: {path}")
            record = records.setdefault(path, dict(path=path, before=before, roles=[], modes=[], guards=[]))
            record["guards"].extend(guards)
            if name == "AGENTS.override.md" and not data.strip():
                continue
            role = {"AGENTS.md": "agents", "CLAUDE.md": "claude", "AGENTS.override.md": "codex-override"}[name]
            record["roles"].append(role)
            record["modes"].append("import" if name == "CLAUDE.md" and before is None else
                                   "preserve" if name == "CLAUDE.md" and span is None and active_agents_import(data) else "early")
        inactive = []
        for record in records.values():
            if not record["roles"]:
                inactive.append((record["path"], record["before"]))
                continue
            before = record["before"]
            data = before[0] if before else b""
            after = early_policy(policy, data) if "early" in record["modes"] else \
                    b"@AGENTS.md\n" if "import" in record["modes"] else data
            rows.append(dict(agent=f"repo-{index}-" + "+".join(record["roles"]),
                             path=record["path"], before=before, after=after,
                             status="ok" if data == after else "drift",
                             alias_guards=record["guards"], repository=root,
                             root_identity=identity))
        # An override appearing or becoming nonempty during planning can hide
        # AGENTS.md, even when the override itself needed no modification.
        first = next(row for row in rows if row["repository"] == root)
        first["watched_files"] = inactive
    return rows


def unchanged(rows: list[dict]) -> None:
    for row in rows:
        if "root_identity" in row:
            root = row["repository"]
            if repository_identity(root) != row["root_identity"]:
                raise ValueError(f"repository root changed concurrently: {root}")
        for path, before in row.get("alias_guards", []):
            if alias_snapshot(path) != before:
                raise ValueError(f"instruction alias changed concurrently: {path}")
        for path, before in row.get("watched_files", []):
            if snapshot(path) != before:
                raise ValueError(f"instruction file changed concurrently: {path}")
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
    selectors = parser.add_mutually_exclusive_group()
    selectors.add_argument("--home", type=Path, help="fixture home; ignore agent environment overrides")
    selectors.add_argument("--repo", type=Path, action="append", help="register portable root instructions in this Git repository (repeatable)")
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
        rows = repository_plan(policy, args.repo) if args.repo else \
               plan(policy, targets(args.home or Path.home(), args.home is not None))
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
