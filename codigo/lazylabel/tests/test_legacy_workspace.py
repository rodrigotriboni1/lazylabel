import json
import tempfile
import unittest
from pathlib import Path

from lazylabel.adapters.outbound.persistence.projects import _config_path
from lazylabel.adapters.outbound.training.backend import _artifact_tree_sha256, read_training_metadata


class LegacyWorkspaceTest(unittest.TestCase):
    """Projects and adapters written before the FinLabel → LazyLabel rename stay readable."""

    def test_project_in_legacy_folder_is_found_and_new_projects_use_new_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(_config_path(root).parent.name, ".lazylabel")
            (root / ".finlabel").mkdir()
            (root / ".finlabel" / "project.json").write_text("{}")
            self.assertEqual(_config_path(root), (root / ".finlabel" / "project.json").resolve())

    def test_legacy_adapter_metadata_is_read_and_excluded_from_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter = Path(tmp)
            (adapter / "weights.bin").write_bytes(b"w")
            before = _artifact_tree_sha256(adapter)
            (adapter / "finlabel-training.json").write_text(json.dumps({"base_model_ref": "m"}))
            self.assertEqual(read_training_metadata(adapter), {"base_model_ref": "m"})
            self.assertEqual(_artifact_tree_sha256(adapter), before)
