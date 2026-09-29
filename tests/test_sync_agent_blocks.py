import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from helpers import ROOT, load_script

sync = load_script("sync-agent-blocks")

CANONICAL = """# Guidelines

<!-- hraness-public-copy:start -->
- Copy rule.
<!-- hraness-public-copy:end -->

<!-- hraness-releases:start -->
- Release rule.
<!-- hraness-releases:end -->

<!-- hraness-articles:start -->
- Article rule.
<!-- hraness-articles:end -->

<!-- hraness-launch:start -->
- Launch rule.
<!-- hraness-launch:end -->

<!-- hraness-delivery:start -->
- Delivery rule.
<!-- hraness-delivery:end -->

<!-- hraness-ci:start -->
- CI rule.
<!-- hraness-ci:end -->

<!-- algal-skills:start -->
not ours
<!-- algal-skills:end -->
"""


class SyncAgentBlocksTest(unittest.TestCase):
    def setUp(self):
        self.canonical = sync.blocks(CANONICAL)

    def test_parses_only_hraness_blocks(self):
        self.assertEqual(sorted(self.canonical), ["hraness-articles", "hraness-ci", "hraness-delivery", "hraness-launch", "hraness-public-copy", "hraness-releases"])
        self.assertEqual(self.canonical["hraness-ci"], "- CI rule.")

    def test_applicability_rules(self):
        repo = "<!-- hraness-delivery:start -->\n- Delivery rule.  \n\n<!-- hraness-delivery:end -->\n<!-- hraness-public-copy:start -->\n- Old copy rule.\n<!-- hraness-public-copy:end -->\n"
        status = sync.compare(self.canonical, repo, {"workflows": True, "releases": False})
        self.assertEqual(status, {
            "hraness-public-copy": "drift", "hraness-releases": "n/a", "hraness-articles": "n/a",
            "hraness-launch": "n/a", "hraness-delivery": "ok", "hraness-ci": "missing"})
        self.assertEqual(sync.compare(self.canonical, repo, {"workflows": False, "releases": True})["hraness-ci"], "n/a")
        self.assertEqual(sync.compare(self.canonical, repo, {"workflows": False, "releases": True})["hraness-releases"], "missing")
        self.assertEqual(sync.compare(self.canonical, repo, {"workflows": False, "releases": None})["hraness-releases"], "n/a")

    def test_launch_required_with_articles(self):
        repo = "<!-- hraness-articles:start -->\n- Article rule.\n<!-- hraness-articles:end -->\n"
        status = sync.compare(self.canonical, repo, {"workflows": False, "releases": False})
        self.assertEqual((status["hraness-articles"], status["hraness-launch"]), ("ok", "missing"))

    def test_conditional_block_present_must_match(self):
        repo = "<!-- hraness-launch:start -->\n- Stale launch rule.\n<!-- hraness-launch:end -->\n"
        self.assertEqual(sync.compare(self.canonical, repo, {"workflows": False})["hraness-launch"], "drift")

    def test_repository_additions_are_ignored(self):
        repo = "<!-- hraness-ci:start -->\n- CI rule.\n<!-- hraness-ci:additions -->\n- This repository also runs X.\n<!-- hraness-ci:end -->\n"
        self.assertEqual(sync.compare(self.canonical, repo, {"workflows": True})["hraness-ci"], "ok")

    def test_missing_agents_md(self):
        status = sync.compare(self.canonical, None, {"workflows": True, "releases": False})
        self.assertEqual(status["hraness-delivery"], "missing")
        self.assertEqual(status["hraness-articles"], "n/a")

    def test_check_on_local_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            canonical = Path(tmp) / "AGENTS.md"
            canonical.write_text(CANONICAL)
            current = Path(tmp) / "current"
            (current / ".github" / "workflows").mkdir(parents=True)
            (current / ".github" / "workflows" / "ci.yml").write_text("on: push\n")
            (current / "AGENTS.md").write_text(CANONICAL.replace("- Launch rule.", "- Launch rule.\n<!-- hraness-launch:additions -->\n- Extra."))
            stale = Path(tmp) / "stale"
            stale.mkdir()
            (stale / "AGENTS.md").write_text(CANONICAL.replace("- Delivery rule.", "- Old delivery rule."))
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(sync.main(["--check", "--canonical", str(canonical), "--path", str(current)]), 0)
            self.assertIn("0 of 1", out.getvalue())
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(sync.main(["--check", "--canonical", str(canonical), "--path", str(current), "--path", str(stale)]), 1)
            self.assertIn("stale", out.getvalue())
            self.assertIn("| drift |", out.getvalue())

    def test_canonical_file_has_the_distributed_blocks(self):
        names = set(sync.blocks((ROOT / "AGENTS.md").read_text()))
        self.assertTrue({"hraness-delivery", "hraness-ci", "hraness-public-copy"} <= names)


if __name__ == "__main__":
    unittest.main()
