import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from finlabel.training.autopipeline import evaluate_post_promotion_health


class PostPromotionHealthTests(unittest.TestCase):
    def test_health_entry_point_uses_shared_registry_decision(self):
        project = SimpleNamespace(workspace_dir=Path("/tmp/finlabel-workspace"))
        health_evaluation = {"evaluation_id": "a" * 32}
        event = object()
        registry = SimpleNamespace(rollback_if_unhealthy=lambda task_id, evaluation: event)
        with patch("finlabel.training.autopipeline.ModelRegistry", return_value=registry) as factory:
            result = evaluate_post_promotion_health(project, "risk", health_evaluation)

        factory.assert_called_once_with(project.workspace_dir)
        self.assertIs(result, event)


if __name__ == "__main__":
    unittest.main()
