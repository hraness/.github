import importlib.util
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
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


class RepositoryRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name).resolve()
        self.repo = self.create_repo("repo")

    def create_repo(self, name):
        path = self.home / name
        path.mkdir(parents=True)
        subprocess.run(["git", "init", "--quiet", str(path)], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")})
        return path

    def put(self, name, data, repo=None):
        path = (repo or self.repo) / name
        path.write_bytes(data)
        return path

    def register(self, repos=None, backup="backups"):
        rows = registration.repository_plan(POLICY, repos or [self.repo])
        registration.write(rows, self.home / backup)
        return rows

    def test_rule_is_first_with_large_existing_files_and_preserves_bytes_and_modes(self):
        prefix = b"Private instructions\r\n\xff\n" + b"x" * 17000 + b"\r\n"
        suffix = b"\r\nUnmanaged ending\x80"
        originals = {}
        for name in ["AGENTS.md", "CLAUDE.md", "AGENTS.override.md"]:
            original = prefix + POLICY.replace(b"provisioned", b"old") + suffix
            path = self.put(name, original)
            path.chmod(0o640)
            originals[path] = original
        unrelated = self.put("README.md", b"Unrelated\xff\r\n")
        rows = self.register()
        self.assertEqual(len(rows), 3)
        for row in rows:
            path = row["path"]
            self.assertEqual(path.read_bytes(), POLICY + b"\n\n" + prefix + suffix)
            self.assertIn(POLICY, path.read_bytes()[:16384])
            self.assertEqual(path.stat().st_mode & 0o777, 0o640)
            self.assertEqual(Path(row["backup"]).read_bytes(), originals[path])
        self.assertEqual(unrelated.read_bytes(), b"Unrelated\xff\r\n")
        before = {row["path"]: registration.snapshot(row["path"]) for row in rows}
        again = self.register(backup="unused")
        self.assertTrue(all(row["status"] == "ok" for row in again))
        self.assertFalse((self.home / "unused").exists())
        self.assertEqual(before, {row["path"]: registration.snapshot(row["path"]) for row in again})

    def test_absent_claude_gets_only_root_import_and_blank_override_is_preserved(self):
        empty_override = self.put("AGENTS.override.md", b" \r\n")
        before = registration.snapshot(empty_override)
        rows = self.register()
        self.assertEqual((self.repo / "AGENTS.md").read_bytes(), POLICY + b"\n")
        self.assertEqual((self.repo / "CLAUDE.md").read_bytes(), b"@AGENTS.md\n")
        self.assertEqual(registration.snapshot(empty_override), before)
        self.assertEqual(len(rows), 2)

    def test_existing_active_import_keeps_claude_file_unchanged(self):
        examples = [b"@AGENTS.md\n", b"Private\xff\r\n@./AGENTS.md\r\nEnding",
                    b"  @AGENTS.md  \r\n", b"   @./AGENTS.md\n",
                    b"<!--\n```\n-->\n@AGENTS.md\n",
                    b"<!--\n    -->\n@AGENTS.md\n",
                    b"```text\n<!--\n```\n@./AGENTS.md\n"]
        for index, original in enumerate(examples):
            with self.subTest(original=original):
                path = self.put("CLAUDE.md", original)
                before = registration.snapshot(path)
                self.register(backup=f"backup-{index}")
                self.assertEqual(registration.snapshot(path), before)

    def test_code_and_commented_imports_do_not_hide_rule_from_claude(self):
        examples = [b"```md\n@AGENTS.md\n```\n", b"~~~\n@./AGENTS.md\n~~~\n",
                    b"   ```md\n@AGENTS.md\n   ```\n",
                    b"````\n```\n@AGENTS.md\n````\n",
                    b"    @AGENTS.md\n", b"\t@./AGENTS.md\n", b" \t@AGENTS.md\n",
                    b"<!--\n@AGENTS.md\n-->\n", b"<!-- @./AGENTS.md -->\n",
                    b"`@AGENTS.md`\n", b"Example: @AGENTS.md\n", b"```\n@AGENTS.md\n"]
        for index, original in enumerate(examples):
            with self.subTest(original=original):
                path = self.put("CLAUDE.md", original)
                self.register(backup=f"backup-{index}")
                self.assertEqual(path.read_bytes(), POLICY + b"\n\n" + original)

    def test_existing_claude_managed_block_is_repaired_even_with_active_import(self):
        prefix, suffix = b"@AGENTS.md\r\nPrivate\xff\n", b"\r\nUnmanaged ending"
        for existing in [POLICY, POLICY.replace(b"provisioned", b"old")]:
            with self.subTest(existing=existing):
                original = prefix + existing + suffix
                claude = self.put("CLAUDE.md", original)
                self.register()
                self.assertEqual(claude.read_bytes(), POLICY + b"\n\n" + prefix + suffix)

    def test_safe_root_symlink_chain_is_coalesced_and_links_are_preserved(self):
        original = b"Private native instructions\xff\r\n"
        target = self.put("AGENTS.override.md", original)
        (self.repo / "CLAUDE.md").symlink_to("AGENTS.override.md")
        (self.repo / "AGENTS.md").symlink_to("CLAUDE.md")
        links = {name: os.readlink(self.repo / name) for name in ["AGENTS.md", "CLAUDE.md"]}
        rows = self.register()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["path"], target)
        self.assertEqual(Path(rows[0]["backup"]).read_bytes(), original)
        for name, link in links.items():
            self.assertTrue((self.repo / name).is_symlink())
            self.assertEqual(os.readlink(self.repo / name), link)
            self.assertEqual((self.repo / name).read_bytes(), POLICY + b"\n\n" + original)
        self.assertTrue(all(row["status"] == "ok" for row in self.register(backup="unused")))
        self.assertFalse((self.home / "unused").exists())

    def test_claude_import_alias_and_override_share_one_safe_write(self):
        original = b"@AGENTS.md\nPrivate guidance\n"
        claude = self.put("CLAUDE.md", original)
        (self.repo / "AGENTS.override.md").symlink_to("CLAUDE.md")
        rows = self.register()
        self.assertEqual(len(rows), 2)
        self.assertEqual(claude.read_bytes(), POLICY + b"\n\n" + original)
        self.assertTrue((self.repo / "AGENTS.override.md").is_symlink())

    def test_unsafe_aliases_and_nonregular_files_prevent_all_writes(self):
        private = self.home / "private"
        private.write_bytes(b"Private contents")
        cases = [private, self.repo / "missing", self.repo / "AGENTS.md"]
        for target in cases:
            with self.subTest(target=target):
                path = self.repo / "AGENTS.md"
                path.symlink_to(target)
                with self.assertRaises(ValueError):
                    self.register()
                path.unlink()
                self.assertFalse((self.repo / "CLAUDE.md").exists())
                self.assertFalse((self.home / "backups").exists())
        (self.repo / "AGENTS.md").symlink_to("CLAUDE.md")
        (self.repo / "CLAUDE.md").symlink_to("AGENTS.md")
        with self.assertRaises(ValueError):
            self.register()
        (self.repo / "AGENTS.md").unlink()
        (self.repo / "CLAUDE.md").unlink()
        (self.repo / "AGENTS.override.md").mkdir()
        with self.assertRaises(ValueError):
            self.register()
        self.assertEqual(private.read_bytes(), b"Private contents")

    def test_nonroot_internal_alias_and_hardlink_alias_are_rejected(self):
        other = self.put("OTHER.md", b"Private contents")
        path = self.repo / "AGENTS.md"
        path.symlink_to("OTHER.md")
        with self.assertRaises(ValueError):
            self.register()
        path.unlink()
        agents = self.put("AGENTS.md", b"Shared hardlink contents")
        os.link(agents, self.repo / "CLAUDE.md")
        with self.assertRaisesRegex(ValueError, "hard.link"):
            self.register()
        self.assertEqual(agents.read_bytes(), b"Shared hardlink contents")
        self.assertEqual(other.read_bytes(), b"Private contents")
        self.assertFalse((self.home / "backups").exists())

    def test_instruction_hardlinked_to_unselected_file_is_rejected(self):
        outside = self.home / "outside-instructions"
        outside.write_bytes(b"Shared outside instructions")
        os.link(outside, self.repo / "AGENTS.md")
        with self.assertRaisesRegex(ValueError, "hard.link"):
            self.register()
        self.assertEqual(outside.read_bytes(), b"Shared outside instructions")
        self.assertFalse((self.repo / "CLAUDE.md").exists())
        self.assertFalse((self.home / "backups").exists())

    def test_bad_last_repository_target_and_malformed_import_file_prevent_all_writes(self):
        last = self.create_repo("last")
        for bad in [registration.START, registration.END, POLICY + POLICY,
                    registration.END + registration.START]:
            with self.subTest(bad=bad):
                self.put("AGENTS.override.md", bad, last)
                with self.assertRaises(ValueError):
                    self.register([self.repo, last])
                self.assertFalse((self.repo / "AGENTS.md").exists())
                self.assertFalse((last / "CLAUDE.md").exists())
                self.assertFalse((self.home / "backups").exists())
        self.put("CLAUDE.md", b"@AGENTS.md\n" + registration.START)
        with self.assertRaises(ValueError):
            self.register()
        self.assertFalse((self.repo / "AGENTS.md").exists())

    def test_preserved_import_and_blank_override_have_concurrency_checks(self):
        for name, original, changed in [("CLAUDE.md", b"@AGENTS.md\n", b"Changed import\n"),
                                        ("AGENTS.override.md", b"", b"New override\n")]:
            with self.subTest(name=name):
                path = self.put(name, original)
                rows = registration.repository_plan(POLICY, [self.repo])
                path.write_bytes(changed)
                with self.assertRaisesRegex(ValueError, "concurrently"):
                    registration.write(rows, self.home / "backups")
                self.assertFalse((self.repo / "AGENTS.md").exists())
                self.assertFalse((self.home / "backups").exists())
                path.unlink()
        rows = registration.repository_plan(POLICY, [self.repo])
        self.put("AGENTS.override.md", b"New override")
        with self.assertRaisesRegex(ValueError, "concurrently"):
            registration.write(rows, self.home / "backups")
        self.assertFalse((self.repo / "AGENTS.md").exists())

    def test_changed_alias_prevents_all_writes(self):
        agents = self.put("AGENTS.md", b"Before")
        claude = self.repo / "CLAUDE.md"
        claude.symlink_to("AGENTS.md")
        rows = registration.repository_plan(POLICY, [self.repo])
        claude.unlink()
        claude.symlink_to("AGENTS.override.md")
        with self.assertRaisesRegex(ValueError, "concurrently"):
            registration.write(rows, self.home / "backups")
        self.assertEqual(agents.read_bytes(), b"Before")
        self.assertFalse((self.home / "backups").exists())

    def test_changed_root_or_gitfile_prevents_first_write(self):
        metadata = self.home / "git-metadata"
        (self.repo / ".git").rename(metadata)
        marker = self.repo / ".git"
        marker.write_text("gitdir: ../git-metadata\n")
        rows = registration.repository_plan(POLICY, [self.repo])
        marker.write_text("gitdir: ../different-metadata\n")
        with self.assertRaisesRegex(ValueError, "concurrently"):
            registration.write(rows, self.home / "backups")
        self.assertFalse((self.repo / "AGENTS.md").exists())
        marker.write_text("gitdir: ../git-metadata\n")
        rows = registration.repository_plan(POLICY, [self.repo])
        self.repo.rename(self.home / "moved-repo")
        self.repo.mkdir()
        (self.repo / ".git").mkdir()
        with self.assertRaisesRegex(ValueError, "concurrently"):
            registration.write(rows, self.home / "backups")
        self.assertFalse((self.repo / "AGENTS.md").exists())
        self.assertFalse((self.home / "backups").exists())

    def test_multi_repo_backups_keep_each_original_file(self):
        second = self.create_repo("second")
        originals = {}
        for index, repo in enumerate([self.repo, second], 1):
            for name in ["AGENTS.md", "CLAUDE.md", "AGENTS.override.md"]:
                path = self.put(name, f"Repository {index} {name}\n".encode(), repo)
                originals[path] = path.read_bytes()
        rows = self.register([self.repo, second])
        self.assertEqual(len(rows), 6)
        self.assertEqual(len({row["backup"] for row in rows}), 6)
        for row in rows:
            self.assertEqual(Path(row["backup"]).read_bytes(), originals[row["path"]])
            self.assertTrue(row["path"].read_bytes().startswith(POLICY))

    def test_only_real_git_roots_are_accepted_and_gitfile_is_supported(self):
        fake = self.home / "fake"
        fake.mkdir()
        (fake / ".git").mkdir()
        nested = self.repo / "nested"
        nested.mkdir()
        for invalid in [fake, nested, self.home, self.home / "missing"]:
            with self.subTest(invalid=invalid), patch.dict(os.environ, {"GIT_DIR": str(self.repo / ".git"),
                                                                       "GIT_WORK_TREE": str(invalid)}):
                with self.assertRaises(ValueError):
                    registration.repository_plan(POLICY, [invalid])
        metadata = self.home / "git-metadata"
        (self.repo / ".git").rename(metadata)
        (self.repo / ".git").write_text("gitdir: ../git-metadata\n")
        self.register()
        self.assertTrue((self.repo / "AGENTS.md").read_bytes().startswith(POLICY))

    def test_overlapping_repo_roots_are_rejected_before_writes(self):
        alias = self.home / "alias"
        alias.symlink_to(self.repo, target_is_directory=True)
        nested = self.create_repo("repo/nested")
        for selected in [[self.repo, self.repo], [self.repo, alias], [self.repo, nested]]:
            with self.subTest(selected=selected), self.assertRaisesRegex(ValueError, "overlap"):
                registration.repository_plan(POLICY, selected)
        self.assertFalse((self.repo / "AGENTS.md").exists())
        self.assertFalse((nested / "AGENTS.md").exists())

    def test_oversized_policy_is_rejected_before_any_write(self):
        large = registration.START + b"\n" + b"x" * 16384 + b"\n" + registration.END
        with self.assertRaisesRegex(ValueError, "16 KiB"):
            registration.repository_plan(large, [self.repo])
        self.assertFalse((self.repo / "AGENTS.md").exists())

    def test_cli_repeated_repo_selector_is_scoped_and_excludes_home(self):
        second = self.create_repo("second")
        global_target = self.home / ".codex/AGENTS.md"
        global_target.parent.mkdir()
        global_target.write_bytes(b"Global untouched\xff")
        canonical = self.home / "source/AGENTS.md"
        canonical.parent.mkdir()
        canonical.write_bytes(POLICY)
        args = ["--repo", str(self.repo), "--repo", str(second), "--json"]
        with patch.object(registration, "__file__", str(canonical.parent / "scripts/register-browser-policy.py")), patch.dict(os.environ, {"CODEX_HOME": str(global_target.parent)}):
            for mode, expected in [("--check", 1), ("--dry-run", 0), ("--write", 0), ("--check", 0)]:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = registration.main(args + [mode, "--backup-dir", str(self.home / "backups")])
                self.assertEqual(code, expected)
                report = json.loads(output.getvalue())
                self.assertEqual(len(report["targets"]), 4)
                self.assertEqual(len({row["agent"] for row in report["targets"]}), 4)
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                registration.main(args + ["--home", str(self.home)])
            self.assertEqual(error.exception.code, 2)
        self.assertEqual(global_target.read_bytes(), b"Global untouched\xff")
        saved = list((self.home / "backups").glob("browser-policy-*/*.md"))
        self.assertEqual(saved, [])  # All four instruction files were new.


if __name__ == "__main__":
    unittest.main()
