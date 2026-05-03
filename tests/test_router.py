from __future__ import annotations

import unittest

from codex_agent.config import load_settings
from codex_agent.router import ModelRouter, classify_task


class StubProvider:
    def __init__(self, models):
        self._models = models

    def available_models(self):
        return list(self._models)


class RouterTests(unittest.TestCase):
    def test_classify_task_prefers_debug_keywords(self) -> None:
        settings = load_settings()
        task_type = classify_task("debug this traceback and fix the crash", settings)
        self.assertEqual(task_type, "debug")

    def test_router_picks_codellama_for_refactor(self) -> None:
        settings = load_settings()
        providers = {
            "ollama": StubProvider(["codellama:7b", "mistral:latest", "phi3:latest"]),
            "open_interpreter": StubProvider([]),
        }
        router = ModelRouter(settings, providers)
        decision = router.route("refactor")
        self.assertEqual(decision.model, "codellama:7b")

    def test_classify_task_ignores_windows_path_noise(self) -> None:
        settings = load_settings()
        task_type = classify_task(
            "Explain C:\\Users\\Administrator\\AI_SYSTEM\\controller.py in 3 bullets",
            settings,
        )
        self.assertEqual(task_type, "explain")


if __name__ == "__main__":
    unittest.main()
