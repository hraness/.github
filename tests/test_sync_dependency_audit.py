import base64
import io
import json
import re
import unittest
from contextlib import redirect_stdout

from helpers import ROOT, load_script

sync = load_script("sync-dependency-audit")
lint = load_script("ci-cost-lint")

SHA = "a" * 40
OLD = "b" * 40


class Template(unittest.TestCase):
    def test_render_pins_one_full_commit(self):
        text = sync.render(SHA)
        self.assertIn(f"- uses: hraness/.github/actions/dependency-audit@{SHA} # main", text)
        self.assertNotIn(sync.PLACEHOLDER, text)
        with self.assertRaises(ValueError):
            sync.render("main")

    def test_pull_request_and_push_paths_list_every_scanned_lockfile(self):
        text = sync.render(SHA)
        expected = [f'"**/{glob}"' for glob in sync.lockfile_globs()] + ['"**/osv-scanner.toml"', ".github/workflows/dependency-audit.yml"]
        blocks = re.findall(r"    paths:\n((?:      - .+\n)+)", text)
        self.assertEqual(len(blocks), 2)
        for block in blocks:
            self.assertEqual([line.removeprefix("      - ") for line in block.splitlines()], expected)

    def test_rendered_workflow_passes_the_cost_lint_in_a_private_repository(self):
        self.assertEqual(lint.lint_workflow("dependency-audit.yml", sync.render(SHA)), [])

    def test_workflow_is_advisory_and_least_privileged(self):
        text = sync.render(SHA)
        self.assertIn("permissions:\n  contents: read\n", text)
        self.assertIn("      contents: read\n      issues: write\n", text)
        self.assertNotIn("Required", text)
        self.assertIn("persist-credentials: false", text)
        for uses in re.findall(r"uses: (\S+)", text):
            self.assertRegex(uses, r"@[0-9a-f]{40}$")


class Lockfiles(unittest.TestCase):
    def test_matching_follows_the_shared_list(self):
        globs = sync.lockfile_globs()
        for path in ["bun.lock", "site/bun.lock", "a/Cargo.lock", "requirements.txt", "api/dev-requirements.txt", "x/go.mod", "App.deps.json"]:
            self.assertTrue(sync.is_lockfile(path, globs), path)
        for path in ["node_modules/a/bun.lock", "bun.lock.bak", "Cargo.toml", "package.json", "go.sum"]:
            self.assertFalse(sync.is_lockfile(path, globs), path)

    def test_the_action_reads_the_same_list(self):
        source = (ROOT / "actions" / "dependency-audit" / "index.mjs").read_text()
        self.assertIn("new URL('./lockfiles.json', import.meta.url)", source)
        self.assertEqual(len(set(sync.lockfile_globs())), len(sync.lockfile_globs()))


class Classify(unittest.TestCase):
    def test_statuses(self):
        expected = sync.render(SHA)
        self.assertEqual(sync.classify(expected, expected, True), "ok")
        self.assertEqual(sync.classify(sync.render(OLD), expected, True), "outdated")
        self.assertEqual(sync.classify(expected.replace("37 5 * * *", "0 0 * * *"), expected, True), "drifted")
        self.assertEqual(sync.classify(None, expected, True), "missing")
        self.assertEqual(sync.classify(None, expected, False), "not-applicable")
        self.assertEqual(sync.classify(expected, expected, False), "not-applicable")

    def test_a_dependabot_checkout_update_is_still_current(self):
        expected = sync.render(SHA)
        bumped = expected.replace("actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1", f"actions/checkout@{'d' * 40} # v7.1.0")
        self.assertNotEqual(bumped, expected)
        self.assertEqual(sync.classify(bumped, expected, True), "ok")
        self.assertEqual(sync.classify(bumped.replace(f"@{SHA}", f"@{OLD}"), expected, True), "outdated")
        self.assertEqual(sync.classify(expected.replace("# v7.0.1", "# main"), expected, True), "drifted")


class FakeGitHub:
    def __init__(self, repos):
        self.repos = repos
        self.writes = []

    def __call__(self, path, paginate=False, method="GET", body=None):
        if method != "GET":
            self.writes.append((method, path, body))
            if path.endswith("/pulls"):
                return {"html_url": f"https://github.com/{path.split('/')[1]}/{path.split('/')[2]}/pull/1"}
            return {}
        if path.startswith("repos/hraness/.github/commits"):
            return [{"sha": SHA}]
        if path.startswith("orgs/"):
            return [{"full_name": f"hraness/{name}", "default_branch": "main", "archived": False, "fork": name == "fork"} for name in self.repos]
        name = path.split("/")[2]
        repo = self.repos.get(name, {})
        if "/git/trees/" in path:
            return {"tree": [{"path": p, "type": "blob"} for p in repo.get("files", [])], "truncated": False}
        if "/contents/.github/workflows/dependency-audit.yml" in path:
            text = repo.get("workflow")
            return {"content": base64.b64encode(text.encode()).decode(), "sha": "blob"} if text else None
        if "/actions/workflows/" in path:
            return {"workflow_runs": [{"conclusion": "failure", "event": "schedule", "html_url": "u", "created_at": "t"}]}
        if "/issues?" in path:
            return [{"number": 3, "title": "Dependency audit: 2 known vulnerabilities (2 high)", "html_url": "i"}]
        if "/pulls?" in path:
            return []
        if "/git/ref/heads/main" in path:
            return {"object": {"sha": "c" * 40}}
        if "/git/ref/heads/" in path:
            return None
        return None


class Main(unittest.TestCase):
    def run_main(self, fake, *argv):
        original_api, original_run = sync.gh_api, sync.run
        sync.gh_api = fake
        sync.run = lambda cmd, stdin=None: type("R", (), {"returncode": 0, "stderr": "", "stdout": ""})()
        out = io.StringIO()
        try:
            with redirect_stdout(out):
                code = sync.main(list(argv))
        finally:
            sync.gh_api, sync.run = original_api, original_run
        return code, out.getvalue()

    def repos(self):
        return {
            "current": {"files": ["bun.lock"], "workflow": sync.render(SHA)},
            "stale": {"files": ["site/bun.lock"], "workflow": sync.render(OLD)},
            "custom": {"files": ["Cargo.lock"], "workflow": "name: Dependency audit\n"},
            "absent": {"files": ["uv.lock", "README.md"]},
            "docs": {"files": ["README.md"]},
            "fork": {"files": ["bun.lock"]},
        }

    def test_check_reports_every_status_and_fails_on_gaps(self):
        code, out = self.run_main(FakeGitHub(self.repos()), "--check", "--org", "hraness", "--json")
        self.assertEqual(code, 1)
        results = {r["repo"]: r for r in json.loads(out)["results"]}
        self.assertEqual({name: r["status"] for name, r in results.items()}, {
            "hraness/absent": "missing", "hraness/current": "ok", "hraness/custom": "drifted",
            "hraness/docs": "not-applicable", "hraness/stale": "outdated",
        })
        self.assertEqual(results["hraness/current"]["issue"]["number"], 3)
        self.assertEqual(results["hraness/current"]["run"]["conclusion"], "failure")

    def test_check_passes_when_every_applicable_repository_is_current(self):
        repos = {"current": {"files": ["bun.lock"], "workflow": sync.render(SHA)}, "docs": {"files": []}}
        code, out = self.run_main(FakeGitHub(repos), "--check", "--org", "hraness")
        self.assertEqual(code, 0)
        self.assertIn("1 ok, 0 outdated, 0 drifted, 0 missing, 1 not-applicable", out)

    def test_apply_opens_pull_requests_only_for_gaps(self):
        fake = FakeGitHub(self.repos())
        code, _ = self.run_main(fake, "--apply", "--org", "hraness", "--include-forks")
        self.assertEqual(code, 0)
        pulls = sorted(path for method, path, _ in fake.writes if path.endswith("/pulls"))
        self.assertEqual(pulls, ["repos/hraness/absent/pulls", "repos/hraness/custom/pulls", "repos/hraness/fork/pulls", "repos/hraness/stale/pulls"])
        puts = [(path, body) for method, path, body in fake.writes if method == "PUT"]
        self.assertTrue(all(body["branch"] == f"hraness/dependency-audit-{SHA[:12]}" for _, body in puts))
        self.assertTrue(all(base64.b64decode(body["content"]).decode() == sync.render(SHA) for _, body in puts))
        self.assertFalse(any("/git/refs/heads/main" in path or body and body.get("branch") == "main" for _, path, body in fake.writes))


if __name__ == "__main__":
    unittest.main()
