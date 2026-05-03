from __future__ import annotations

import unittest

from codex_agent.config import load_settings
from codex_agent.project import ProjectAnalyzer
from codex_agent.tools import ToolRegistry


class ToolRegistryTests(unittest.TestCase):
    def test_run_command_blocks_dangerous_command(self) -> None:
        settings = load_settings()
        analyzer = ProjectAnalyzer(settings)
        tools = ToolRegistry(analyzer, settings)
        result = tools.call("run_command", command=["rm", "-rf", "demo"], dry_run=False)
        self.assertFalse(result["executed"])
        self.assertIn("dangerous", result["reason"])

    def test_run_command_stays_dry_run_when_execution_disabled(self) -> None:
        settings = load_settings()
        analyzer = ProjectAnalyzer(settings)
        tools = ToolRegistry(analyzer, settings)
        result = tools.call("run_command", command=["python", "--version"], dry_run=False)
        self.assertFalse(result["executed"])
        self.assertEqual(result["reason"], "dry-run")


if __name__ == "__main__":
    unittest.main()
