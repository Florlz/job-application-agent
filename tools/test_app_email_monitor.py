import subprocess
import sys
import unittest
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parent
SCRIPT = TOOLS_DIR / "app_email_monitor.py"


class AppEmailMonitorTests(unittest.TestCase):
    def test_n8n_unavailable_is_a_quiet_success(self):
        code = f"""
import runpy
import sys
from unittest.mock import patch
from urllib.error import URLError
sys.path.insert(0, {str(TOOLS_DIR)!r})
with patch('urllib.request.urlopen', side_effect=URLError('connection refused')):
    runpy.run_path({str(SCRIPT)!r}, run_name='__main__')
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout)
        self.assertEqual("", result.stderr)


if __name__ == "__main__":
    unittest.main()
