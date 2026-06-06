import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import stability_store as store
from stability_diagnostics import create_diagnostic_bundle, run_health_check


def minimal_chat():
    return {
        "title": "备份测试",
        "case_title": "病例001：测试证",
        "history": [],
        "updated_at": "06-02 00:00",
    }


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory(prefix="shenzhi-diagnostics-")
        self.root = Path(self._tempdir.name)
        self.runtime_dir = self.root / "runtime"
        self.old_runtime_env = os.environ.get("SHENZHI_RUNTIME_DIR")
        os.environ["SHENZHI_RUNTIME_DIR"] = str(self.runtime_dir)
        store.RUNTIME_DIR = self.runtime_dir
        store.DB_PATH = self.runtime_dir / "shenzhi_sessions.db"
        store.LOG_PATH = self.runtime_dir / "shenzhi_app.log"

        (self.root / "cases").mkdir()
        (self.root / "tongue_images").mkdir()
        (self.root / ".streamlit").mkdir()
        (self.root / ".streamlit" / "secrets.toml").write_text(
            'DEEPSEEK_API_KEY = "private-test-key"\n',
            encoding="utf-8",
        )
        case = {
            "case_id": "case_001",
            "title": "病例001：测试证",
            "tcm_info": {"tongue_images": ["tongue_images/case_001.jpg"]},
        }
        (self.root / "cases" / "case_001_测试证.json").write_text(
            json.dumps(case, ensure_ascii=False),
            encoding="utf-8",
        )
        (self.root / "tongue_images" / "case_001.jpg").write_bytes(b"test-image")

    def tearDown(self):
        if self.old_runtime_env is None:
            os.environ.pop("SHENZHI_RUNTIME_DIR", None)
        else:
            os.environ["SHENZHI_RUNTIME_DIR"] = self.old_runtime_env
        self._tempdir.cleanup()

    def test_health_check_validates_cases_images_and_database(self):
        store.save_all_chat_sessions({"backup-test": minimal_chat()}, "backup-test")
        report = run_health_check(self.root, expected_case_count=1)
        checks = {check["name"]: check for check in report["checks"]}

        self.assertEqual("pass", checks["病例库"]["status"])
        self.assertEqual("pass", checks["舌象图片"]["status"])
        self.assertEqual("pass", checks["会话数据库"]["status"])
        self.assertEqual(1, checks["会话数据库"]["details"]["sessions"])

    def test_periodic_backup_creates_snapshot_and_reuses_recent_file(self):
        store.save_all_chat_sessions({"backup-test": minimal_chat()}, "backup-test")
        first_backup = store.ensure_periodic_backup()
        second_backup = store.ensure_periodic_backup()

        self.assertEqual(first_backup, second_backup)
        self.assertTrue(first_backup.exists())
        self.assertEqual(1, len(list((self.runtime_dir / "backups").glob("*.db"))))

    def test_diagnostic_bundle_never_contains_secret_or_raw_database(self):
        store.save_all_chat_sessions({"backup-test": minimal_chat()}, "backup-test")
        store.log_event("diagnostic_test")
        report = run_health_check(self.root, expected_case_count=1)
        bundle_path = create_diagnostic_bundle(self.root, report=report)

        with zipfile.ZipFile(bundle_path) as archive:
            filenames = archive.namelist()
            bundle_text = "\n".join(
                archive.read(filename).decode("utf-8", errors="ignore")
                for filename in filenames
            )

        self.assertNotIn("private-test-key", bundle_text)
        self.assertNotIn("shenzhi_sessions.db", filenames)
        self.assertIn("secrets_status.toml", filenames)


if __name__ == "__main__":
    unittest.main(verbosity=2)
