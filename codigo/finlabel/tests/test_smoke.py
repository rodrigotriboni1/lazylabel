import subprocess
import sys
import unittest


class CliSmokeTest(unittest.TestCase):
    def test_cli_help_exits_zero(self):
        result = subprocess.run(
            [sys.executable, "-m", "finlabel.cli", "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("inspect", result.stdout)


if __name__ == "__main__":
    unittest.main()
