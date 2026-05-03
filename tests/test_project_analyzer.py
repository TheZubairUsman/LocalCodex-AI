from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from codex_agent.config import load_settings
from codex_agent.project import ProjectAnalyzer


class ProjectAnalyzerTests(unittest.TestCase):
    def test_inventory_categorizes_python_and_configs(self) -> None:
        settings = load_settings()
        analyzer = ProjectAnalyzer(settings)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "app.py").write_text("import tkinter\n", encoding="utf-8")
            (root / "config.json").write_text('{"name": "demo"}', encoding="utf-8")
            inventory = analyzer.build_inventory(root)

        self.assertEqual(inventory.total_files, 2)
        self.assertIn("app.py", inventory.category_map["python_files"])
        self.assertIn("config.json", inventory.category_map["config_files"])
        self.assertIn("tkinter_gui", inventory.detected_components)


if __name__ == "__main__":
    unittest.main()
