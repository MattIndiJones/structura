"""Regression checks for CI scope selection; no application or database imports."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import select_tests


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name, source in {
            "test_simulation.py": "from backend.app.core.payscript.simulation import solve_for_param",
            "test_api.py": 'def fixture():\n from backend.app.api import simulation\n',
            "test_client.py": "from backend.app.db.models import Client",
        }.items():
            path = self.root / "backend/tests" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source, encoding="utf-8")

    def test_code_selects_only_direct_consumers(self):
        targets, notes = select_tests.select_backend(self.root, ["backend/app/core/payscript/simulation.py"])
        self.assertEqual(targets, ["backend/tests/test_simulation.py"])
        self.assertEqual(notes, [])

    def test_local_import_and_from_package_are_detected(self):
        targets, _ = select_tests.select_backend(self.root, ["backend/app/api/simulation.py"])
        self.assertEqual(targets, ["backend/tests/test_api.py"])

    def test_shared_model_does_not_select_unrelated_domains(self):
        targets, notes = select_tests.select_backend(self.root, ["backend/app/db/models.py"])
        self.assertEqual(targets, [])
        self.assertTrue(notes)

    def test_changed_tests_are_selected_and_deleted_tests_ignored(self):
        targets, _ = select_tests.select_backend(self.root, ["backend/tests/test_client.py", "backend/tests/test_removed.py"])
        self.assertEqual(targets, ["backend/tests/test_client.py"])

    def test_documentation_does_not_run_backend(self):
        self.assertEqual(select_tests.select_backend(self.root, ["docs/README.md"]), ([], []))

    def test_manual_targets_preserve_node_and_reject_full_suite_or_options(self):
        self.assertEqual(select_tests.manual_targets(self.root, "backend/tests/test_api.py::test_node"), ["backend/tests/test_api.py::test_node"])
        for target in ("backend/tests", "-x", "backend/tests/../../app/main.py"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                select_tests.manual_targets(self.root, target)

    def test_only_manual_full_suite_can_select_test_directory(self):
        event_path = self.root / "event.json"
        event_path.write_text(json.dumps({"inputs": {"full_suite": "true"}}), encoding="utf-8")
        output = self.root / "output"
        env = {"GITHUB_EVENT_PATH": str(event_path), "GITHUB_OUTPUT": str(output),
               "GITHUB_STEP_SUMMARY": str(self.root / "summary"), "GITHUB_EVENT_NAME": "workflow_dispatch"}
        with patch.dict(os.environ, env), patch.object(Path, "cwd", return_value=self.root), patch.object(select_tests, "git", return_value=""):
            select_tests.main()
        self.assertIn('backend_tests=["backend/tests"]', output.read_text(encoding="utf-8"))

    def test_automatic_full_selection_is_refused(self):
        targets, notes = select_tests.select_backend(self.root, ["backend/tests/test_simulation.py", "backend/tests/test_api.py", "backend/tests/test_client.py"])
        self.assertEqual(targets, [])
        self.assertTrue(notes)

    def test_pr_inputs_cannot_request_full_suite(self):
        event_path = self.root / "event.json"
        event_path.write_text(json.dumps({"inputs": {"full_suite": "true"}, "pull_request": {"base": {"sha": "base"}}}), encoding="utf-8")
        output = self.root / "output"
        env = {"GITHUB_EVENT_PATH": str(event_path), "GITHUB_OUTPUT": str(output),
               "GITHUB_STEP_SUMMARY": str(self.root / "summary"), "GITHUB_EVENT_NAME": "pull_request"}
        with patch.dict(os.environ, env), patch.object(Path, "cwd", return_value=self.root), patch.object(select_tests, "git", side_effect=["base", "backend/tests/test_api.py"]):
            select_tests.main()
        self.assertIn('backend_tests=["backend/tests/test_api.py"]', output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
