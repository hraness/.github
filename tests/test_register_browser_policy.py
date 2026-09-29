import importlib.util
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("registration", Path(__file__).resolve().parents[1] / "scripts/register-browser-policy.py")
registration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(registration)
POLICY = registration.START + b"\nUse provisioned browsers.\n" + registration.END


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name).resolve()
        self.selected = registration.targets(self.home, fixture=True)

    def put(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def test_roundtrip_preserves_unmanaged_bytes_mode_and_backup(self):
        original = b"Private instruction\r\n\xff\n"
        for _, path in self.selected:
            self.put(path, original)
            path.chmod(0o640)
        rows = registration.plan(POLICY, self.selected)
        registration.write(rows, self.home / "backups")
        for row in rows:
            path = row["path"]
            self.assertTrue(path.read_bytes().startswith(original))
            self.assertIn(POLICY, path.read_bytes())
            self.assertEqual(path.stat().st_mode & 0o777, 0o640)
            self.assertEqual(Path(row["backup"]).read_bytes(), original)
        before = [registration.snapshot(path) for _, path in self.selected]
        registration.write(registration.plan(POLICY, self.selected), self.home / "unused")
        self.assertFalse((self.home / "unused").exists())
        self.assertEqual(before, [registration.snapshot(path) for _, path in self.selected])

    def test_replacement_preserves_both_sides_and_detects_drift(self):
        path = self.selected[0][1]
        self.put(path, b"prefix\r\n" + POLICY + b"\r\nsuffix\xff")
        changed = POLICY.replace(b"provisioned", b"versioned")
        rows = registration.plan(changed, self.selected)
        self.assertEqual(rows[0]["status"], "drift")
        self.assertEqual(rows[0]["after"], b"prefix\r\n" + changed + b"\r\nsuffix\xff")

    def test_absent_and_blank_files(self):
        self.put(self.selected[0][1], b"")
        self.put(self.selected[1][1], b"\n\n")
        registration.write(registration.plan(POLICY, self.selected), self.home / "backup")
        self.assertTrue(all(r["status"] == "ok" for r in registration.plan(POLICY, self.selected)))

    def test_environment_and_override_selection(self):
        env = {"CODEX_HOME": str(self.home / "cx"), "CLAUDE_CONFIG_DIR": str(self.home / "cl"), "XDG_CONFIG_HOME": str(self.home / "xdg")}
        override = self.home / "cx/AGENTS.override.md"
        self.put(override, b"active")
        with patch.dict(os.environ, env):
            selected = registration.targets(self.home)
            self.assertEqual([p for _, p in selected], [self.home / "cx/AGENTS.md", self.home / "cl/CLAUDE.md", self.home / "xdg/devin/AGENTS.md", override])
            self.assertEqual(registration.targets(self.home, fixture=True), self.selected)
            override.write_bytes(b" \n")
            self.assertEqual(len(registration.targets(self.home)), 3)

    def test_bad_last_target_prevents_all_writes(self):
        for bad in [registration.START, registration.END, POLICY + POLICY, registration.END + registration.START]:
            self.put(self.selected[-1][1], bad)
            with self.assertRaises(ValueError):
                registration.plan(POLICY, self.selected)
            self.assertFalse(self.selected[0][1].exists())

    def test_empty_environment_defaults_and_relative_roots_reject(self):
        names = ["CODEX_HOME", "CLAUDE_CONFIG_DIR", "XDG_CONFIG_HOME"]
        with patch.dict(os.environ, {name: "" for name in names}, clear=True):
            self.assertEqual(registration.targets(self.home), self.selected)
            for name in names:
                with patch.dict(os.environ, {name: "relative/config"}):
                    with self.assertRaisesRegex(ValueError, name + " must be an absolute"):
                        registration.targets(self.home)
        self.assertFalse(any(path.exists() for _, path in self.selected))

    def test_parent_symlink_alias_rejects_overlapping_targets(self):
        shared = self.home / "shared"
        shared.mkdir()
        config = self.home / "xdg"
        config.mkdir()
        (config / "devin").symlink_to(shared, target_is_directory=True)
        with patch.dict(os.environ, {"CODEX_HOME": str(shared), "XDG_CONFIG_HOME": str(config)}, clear=True):
            with self.assertRaisesRegex(ValueError, "targets overlap"):
                registration.targets(self.home)
        self.assertEqual(list(shared.iterdir()), [])

    def test_parent_symlink_is_resolved_without_following_instruction_symlink(self):
        real = self.home / "real"
        real.mkdir()
        alias = self.home / "alias"
        alias.symlink_to(real, target_is_directory=True)
        with patch.dict(os.environ, {"CODEX_HOME": str(alias)}, clear=True):
            selected = registration.targets(self.home)
        self.assertEqual(selected[0][1], real / "AGENTS.md")
        private = self.home / "private"
        private.write_bytes(b"unchanged")
        (real / "AGENTS.md").symlink_to(private)
        with self.assertRaisesRegex(ValueError, "not a regular file"):
            registration.plan(POLICY, selected)
        self.assertEqual(private.read_bytes(), b"unchanged")

    def test_symlink_rejected_including_override(self):
        target = self.home / "private"
        target.write_bytes(b"secret")
        path = self.selected[-1][1]
        path.parent.mkdir(parents=True)
        path.symlink_to(target)
        with self.assertRaises(ValueError):
            registration.plan(POLICY, self.selected)
        override = self.home / ".codex/AGENTS.override.md"
        override.parent.mkdir()
        override.symlink_to(target)
        with self.assertRaises(ValueError):
            registration.targets(self.home, fixture=True)
        self.assertEqual(target.read_bytes(), b"secret")

    def test_concurrent_edit_prevents_first_write(self):
        rows = registration.plan(POLICY, self.selected)
        self.put(self.selected[-1][1], b"concurrent edit")
        with self.assertRaisesRegex(ValueError, "concurrently"):
            registration.write(rows, self.home / "backups")
        self.assertFalse(self.selected[0][1].exists())
        self.assertFalse((self.home / "backups").exists())

    def test_cli_check_dry_run_write_and_json(self):
        canonical = self.home / "source/AGENTS.md"
        self.put(canonical, b"Repository rules\n" + POLICY + b"\n")
        args = ["--home", str(self.home / "fixture"), "--json"]
        with patch.object(registration, "__file__", str(canonical.parent / "scripts/register-browser-policy.py")):
            for mode, expected in [("--check", 1), ("--dry-run", 0), ("--write", 0), ("--check", 0)]:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = registration.main(args + [mode, "--backup-dir", str(self.home / "backup")])
                self.assertEqual(code, expected)
                report = json.loads(output.getvalue())
                self.assertEqual(len(report["policy_sha256"]), 64)
                self.assertEqual(len(report["targets"]), 3)
            self.assertEqual((self.home / "fixture/.codex/AGENTS.md").read_bytes(), POLICY + b"\n")

    def test_partial_write_error_reports_completed_targets_and_backups(self):
        canonical = self.home / "source/AGENTS.md"
        self.put(canonical, POLICY)
        original = b"Unmanaged instructions\n"
        for _, path in self.selected:
            self.put(path, original)
        replace = registration.os.replace
        calls = 0

        def fail_second(source, destination):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated second-file failure")
            return replace(source, destination)

        output = io.StringIO()
        with patch.object(registration, "__file__", str(canonical.parent / "scripts/register-browser-policy.py")), patch.object(registration.os, "replace", side_effect=fail_second), contextlib.redirect_stdout(output):
            code = registration.main(["--home", str(self.home), "--write", "--backup-dir", str(self.home / "backup"), "--json"])
        self.assertEqual(code, 2)
        report = json.loads(output.getvalue())
        self.assertIn("second-file failure", report["error"])
        self.assertEqual([row["status"] for row in report["targets"]], ["updated", "drift", "drift"])
        for row in report["targets"]:
            self.assertEqual(Path(row["backup"]).read_bytes(), original)
        self.assertIn(POLICY, self.selected[0][1].read_bytes())
        self.assertEqual(self.selected[1][1].read_bytes(), original)
        self.assertEqual(self.selected[2][1].read_bytes(), original)
        self.assertEqual(list(self.home.glob(".*/.browser-policy-*")), [])


if __name__ == "__main__":
    unittest.main()
