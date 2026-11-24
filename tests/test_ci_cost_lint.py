import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from helpers import load_script

lint_mod = load_script("ci-cost-lint")


def rules(text, name="ci.yml"):
    return sorted(((f.job, f.rule) for f in lint_mod.lint_workflow(name, text)), key=lambda pair: (pair[0] or "", pair[1]))


CLEAN = """
name: CI
on:
  pull_request:
  push:
    branches: [main]
concurrency:
  group: ci-${{ github.event_name == 'pull_request' && github.ref || github.sha }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/cache/restore@v5
        with: {path: x, key: y}
      - uses: actions/cache/save@v5
        if: github.ref == 'refs/heads/main'
        with: {path: x, key: y}
      - uses: Swatinem/rust-cache@v2
        with:
          save-if: ${{ github.ref == 'refs/heads/main' }}
  native:
    # cost-lint: native-surface (the macOS app)
    runs-on: macos-15
    timeout-minutes: 20
    steps: []
  call:
    uses: ./.github/workflows/reusable.yml
"""


class CiCostLintTest(unittest.TestCase):
    def test_clean_workflow_has_no_findings(self):
        self.assertEqual(rules(CLEAN), [])

    def test_native_runner_without_marker(self):
        text = """
on: pull_request
concurrency: {group: x, cancel-in-progress: true}
jobs:
  cross:
    timeout-minutes: 5
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest, macos-14]
    runs-on: ${{ matrix.os }}
    steps: []
  mac:
    timeout-minutes: 5
    runs-on: [macos-14]
    steps: []
"""
        findings = lint_mod.lint_workflow("ci.yml", text)
        self.assertEqual(sorted((f.job, f.rule) for f in findings), [("cross", "native-runner"), ("mac", "native-runner")])
        self.assertIn("macos-14, windows-latest", findings[0].message)

    def test_missing_concurrency_and_timeout(self):
        text = "on: [push, pull_request]\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps: []\n"
        self.assertEqual(rules(text), [(None, "no-concurrency"), ("a", "no-timeout")])

    def test_job_level_concurrency_counts(self):
        text = "on: schedule\njobs:\n  a:\n    runs-on: ubuntu-slim\n    timeout-minutes: 1\n    concurrency: nightly\n    steps: []\n"
        self.assertEqual(rules(text), [])

    def test_workflow_call_only_is_exempt_from_concurrency(self):
        text = "on:\n  workflow_call:\njobs:\n  a:\n    runs-on: ubuntu-slim\n    timeout-minutes: 1\n    steps: []\n"
        self.assertEqual(rules(text), [])

    def test_push_with_unconditional_cancel(self):
        text = """
on:
  push:
    branches: [main]
  pull_request:
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
jobs:
  a:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps: []
"""
        self.assertEqual(rules(text), [(None, "push-cancel")])
        self.assertEqual(rules(text.replace("  push:\n    branches: [main]\n", "")), [])

    def test_pr_cache_saves(self):
        text = """
on: pull_request
concurrency: {group: x, cancel-in-progress: true}
jobs:
  a:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/cache@v5
        with: {path: x, key: y}
      - uses: actions/cache/save@v5
        with: {path: x, key: y}
      - uses: Swatinem/rust-cache@v2
      - uses: actions/setup-node@v6
        with: {node-version: 24, cache: npm}
      - uses: actions/setup-python@v6
        with: {python-version: "3.12"}
      - uses: astral-sh/setup-uv@v7
        with: {enable-cache: true}
"""
        findings = [f for f in lint_mod.lint_workflow("ci.yml", text) if f.rule == "pr-cache-save"]
        self.assertEqual(len(findings), 5)
        self.assertTrue(any("setup-node" in f.message for f in findings))
        self.assertFalse(any("setup-python" in f.message for f in findings))

    def test_negated_main_guard_still_saves_on_pull_requests(self):
        step = "      - uses: actions/cache/save@v5\n        if: {guard}\n        with: {{path: x, key: y}}\n"
        head = "on: pull_request\nconcurrency: {group: x, cancel-in-progress: true}\njobs:\n  a:\n    runs-on: ubuntu-latest\n    timeout-minutes: 5\n    steps:\n"
        for guard, expected in (
            ("github.ref != 'refs/heads/main'", [("a", "pr-cache-save")]),
            ("github.ref == 'refs/heads/main'", []),
            ('github.ref_name == "main"', []),
        ):
            with self.subTest(guard=guard):
                self.assertEqual(rules(head + step.format(guard=guard)), expected)

    def test_deploy_job_must_not_group_by_sha(self):
        text = """
on:
  push:
    branches: [main]
concurrency:
  group: ci-${{ github.event_name == 'pull_request' && github.ref || github.sha }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}
jobs:
  deploy:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    environment: production
    steps: []
"""
        self.assertEqual(rules(text), [("deploy", "deploy-sha-group")])
        fixed = text.replace("    environment: production\n", "    environment: production\n    concurrency: {group: deploy-production, cancel-in-progress: false}\n")
        self.assertEqual(rules(fixed), [])

    def test_cache_saves_ignored_without_pull_request_trigger(self):
        text = "on:\n  push:\n    branches: [main]\nconcurrency: {group: x, cancel-in-progress: false}\njobs:\n  a:\n    runs-on: ubuntu-latest\n    timeout-minutes: 5\n    steps:\n      - uses: actions/cache@v5\n"
        self.assertEqual(rules(text), [])

    def test_unparseable_workflow_is_reported(self):
        self.assertEqual(rules("on: [push\njobs: {"), [(None, "parse")])

    def test_exit_status_depends_on_visibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            workflows = Path(tmp) / ".github" / "workflows"
            workflows.mkdir(parents=True)
            (workflows / "ci.yml").write_text("on: push\njobs:\n  a:\n    runs-on: macos-14\n    steps: []\n")
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(lint_mod.main([tmp, "--visibility", "public"]), 0)
            self.assertIn("warning:", out.getvalue())
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(lint_mod.main([tmp, "--visibility", "private"]), 1)
            self.assertIn("error:", out.getvalue())
            (workflows / "ci.yml").write_text(CLEAN)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(lint_mod.main([tmp, "--visibility", "private"]), 0)

    def test_this_repository_is_clean(self):
        root = Path(__file__).resolve().parent.parent
        with redirect_stdout(io.StringIO()):
            self.assertEqual(lint_mod.main([str(root), "--visibility", "private"]), 0)


if __name__ == "__main__":
    unittest.main()


RUNNERS = """
on: push
permissions: {contents: read}
jobs:
  deploy:
    runs-on: hraness-cf
    environment: production
    timeout-minutes: 5
    steps: [{run: "echo ${{ secrets.DEPLOY_TOKEN }} ${{ secrets.GITHUB_TOKEN }}"}]
  check:
    runs-on: hraness-cf
    timeout-minutes: 5
    steps: [{run: "echo ${{ secrets.GITHUB_TOKEN }}"}]
  release:
    runs-on: hraness-cf-isolated
    permissions: {contents: write, id-token: write}
    timeout-minutes: 5
    steps: [{run: x}]
  tag:
    runs-on: ${{ matrix.os == 'mac' && 'self-hosted' || 'hraness-cf' }}
    permissions: {contents: write}
    timeout-minutes: 5
    steps: [{run: x}]
  hosted:
    runs-on: ubuntu-24.04
    permissions: {id-token: write}
    timeout-minutes: 5
    steps: [{run: x}]
"""


def runner_rules(visibility):
    return sorted((f.job, f.rule, f.severity) for f in lint_mod.runner_findings("w.yml", RUNNERS, visibility))


class RunnerRules(unittest.TestCase):
    def test_a_private_job_that_holds_a_secret_or_writes_runs_on_the_isolated_label(self):
        self.assertEqual(runner_rules("private"), [("deploy", "shared-secret", "error"), ("tag", "shared-secret", "error")])
        message = next(f.message for f in lint_mod.runner_findings("w.yml", RUNNERS, "private") if f.job == "deploy")
        self.assertIn("DEPLOY_TOKEN", message)
        self.assertNotIn("GITHUB_TOKEN", message)

    def test_a_public_job_never_runs_on_an_owned_runner(self):
        self.assertEqual(runner_rules("public"), [("check", "public-owned", "error"), ("deploy", "public-owned", "error"),
                                                  ("release", "public-owned", "error"), ("tag", "public-owned", "error")])

    def test_runner_errors_fail_a_public_repository_too(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / ".github" / "workflows").mkdir(parents=True)
            (Path(root) / ".github" / "workflows" / "w.yml").write_text(RUNNERS)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(lint_mod.main([root, "--visibility", "public"]), 1)
