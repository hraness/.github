import json
import unittest

from helpers import ROOT, load_script


register = load_script("register-browser-policy")


class BrowserPolicyDistributionTest(unittest.TestCase):
    def test_portable_artifacts_include_the_whole_rule_before_devin_limit(self):
        source = (ROOT / "AGENTS.md").read_bytes()
        start, end = register.bounds(source)
        canonical = source[start:end]
        for path in (ROOT / "AGENTS.md", ROOT / "templates/AGENTS.md", ROOT / "plugins/browser-automation/AGENTS.md"):
            with self.subTest(path=path):
                content = path.read_bytes()
                self.assertTrue(content.startswith(canonical))
                self.assertLessEqual(len(canonical), 16 * 1024)
                self.assertEqual(content.count(register.START), 1)
                self.assertEqual(content.count(register.END), 1)
        self.assertEqual((ROOT / "templates/CLAUDE.md").read_bytes(), b"@AGENTS.md\n")

    def test_devin_plugin_can_only_load_its_rule(self):
        root = ROOT / "plugins/browser-automation"
        files = {str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()}
        self.assertEqual(files, {".devin-plugin/plugin.json", "AGENTS.md"})
        manifest = json.loads((root / ".devin-plugin/plugin.json").read_text())
        self.assertEqual(manifest["name"], "hraness-browser-automation")
        self.assertEqual(manifest["skills"], [])
        self.assertEqual(manifest["mcpServers"], {"paths": [], "exclusive": True})
        for name in ("requiredPlugins", "optionalPlugins", "forbiddenPlugins"):
            self.assertEqual(manifest[name], [])
        self.assertEqual(set(manifest), {"name", "version", "description", "skills", "mcpServers", "requiredPlugins", "optionalPlugins", "forbiddenPlugins"})


if __name__ == "__main__":
    unittest.main()
