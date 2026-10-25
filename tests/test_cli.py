import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from exchange.cli import main


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = str(Path(self.tmp.name) / "data.json")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stderr(err):
            code = main(["--data", self.data, *args], out=out)
        return code, out.getvalue(), err.getvalue()

    def test_full_flow(self):
        self.assertEqual(self.run_cli("init", "--base", "RUB")[0], 0)
        self.assertEqual(self.run_cli("deposit", "RUB", "100000")[0], 0)
        self.assertEqual(self.run_cli("rate", "USD", "90", "92")[0], 0)

        code, out, _ = self.run_cli("buy", "USD", "100")
        self.assertEqual(code, 0)
        self.assertIn("9000.00 RUB", out)

        code, out, _ = self.run_cli("sell", "USD", "50")
        self.assertEqual(code, 0)
        self.assertIn("4600.00 RUB", out)
        self.assertIn("Прибыль по операции: 100.00", out)

        code, out, _ = self.run_cli("balance")
        self.assertIn("95600.00", out)
        self.assertIn("50.00", out)

        code, out, _ = self.run_cli("report")
        self.assertIn("Итого прибыль: 100.00 RUB", out)

        code, out, _ = self.run_cli("history")
        self.assertEqual(len(out.strip().splitlines()), 3)

    def test_quote_does_not_change_state(self):
        self.run_cli("init")
        self.run_cli("rate", "USD", "90", "92")
        before = Path(self.data).read_text(encoding="utf-8")
        code, out, _ = self.run_cli("quote", "sell", "USD", "10")
        self.assertEqual(code, 0)
        self.assertIn("920.00 RUB", out)
        self.assertEqual(Path(self.data).read_text(encoding="utf-8"), before)

    def test_error_is_reported_and_state_kept(self):
        self.run_cli("init")
        self.run_cli("rate", "USD", "90", "92")
        code, _, err = self.run_cli("sell", "USD", "10")
        self.assertEqual(code, 1)
        self.assertIn("Недостаточно USD", err)

    def test_requires_init(self):
        code, _, err = self.run_cli("balance")
        self.assertEqual(code, 1)
        self.assertIn("init", err)

    def test_init_does_not_overwrite(self):
        self.run_cli("init")
        code, _, err = self.run_cli("init")
        self.assertEqual(code, 1)
        self.assertIn("--force", err)
        self.assertEqual(self.run_cli("init", "--force")[0], 0)


if __name__ == "__main__":
    unittest.main()
