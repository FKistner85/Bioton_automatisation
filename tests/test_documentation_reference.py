"""Documentation references must expose real diagnostics without field-name noise."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import documentation_reference as docs
from documentation_error_meanings import meaning


class DocumentationTests(unittest.TestCase):
    def test_checked_in_references_match_sources(self):
        self.assertEqual(docs.update(check=True), [])

    def test_all_diagnostic_codes_have_reviewed_meanings(self):
        codes = {r["value"] for paths in docs.GROUPS.values() for path in paths
                 for r in docs.diagnostics(path) if r["kind"] == "code"}
        self.assertIn("utc_local_conflict", codes)
        self.assertIn("required_models_incomplete", codes)
        self.assertNotIn("issue_codes", codes)
        self.assertNotIn("True", codes)
        for code in codes:
            self.assertTrue(meaning(code, "DE"))
            self.assertTrue(meaning(code, "EN"))

    def test_master_dictionary_covers_current_columns(self):
        import ast
        source = ast.parse((ROOT / "scripts/Step_7_0_update_master_table.py").read_text(encoding="utf-8"))
        # MASTER_COLUMNS appends imported FLAG_COLUMNS; inspect both literals.
        columns = []
        for file, name in [(source, "MASTER_COLUMNS"), (ast.parse((ROOT / "scripts/spatiotemporal_duplicates.py").read_text()), "FLAG_COLUMNS")]:
            for node in file.body:
                if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                    columns.extend(n.value for n in ast.walk(node.value) if isinstance(n, ast.Constant) and isinstance(n.value, str))
        reference = (ROOT / "MASTER_TABLE_README.md").read_text(encoding="utf-8")
        self.assertGreaterEqual(len(columns), 104)
        self.assertEqual([c for c in columns if f"`{c}`" not in reference], [])


if __name__ == "__main__":
    unittest.main()
