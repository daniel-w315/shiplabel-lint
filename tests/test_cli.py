import contextlib
import json
import os
import sys
import tempfile
import unittest
from io import StringIO

from shiplabel_lint.cli import main


class TestCli(unittest.TestCase):
    def _run(self, argv, stdin_text=None):
        out = StringIO()
        old_stdin = sys.stdin
        if stdin_text is not None:
            sys.stdin = StringIO(stdin_text)
        try:
            with contextlib.redirect_stdout(out):
                with self.assertRaises(SystemExit) as cm:
                    main(argv)
        finally:
            sys.stdin = old_stdin
        return cm.exception.code, out.getvalue()

    def test_stdin_clean_manifest_exits_zero_with_no_output(self):
        csv_text = (
            "tracking_number,carrier,weight_oz,dest_postal\n"
            "1Z999AA10123456784,ups,32,60614\n"
        )
        code, output = self._run([], stdin_text=csv_text)
        self.assertEqual(code, 0)
        self.assertEqual(output, "")

    def test_stdin_bad_row_exits_one_and_reports_line(self):
        csv_text = (
            "tracking_number,carrier,weight_oz,dest_postal\n,ups,32,60614\n"
        )
        code, output = self._run([], stdin_text=csv_text)
        self.assertEqual(code, 1)
        self.assertIn("E010", output)
        self.assertIn("<stdin>:2:", output)

    def test_warnings_alone_do_not_fail(self):
        csv_text = (
            "tracking_number,carrier,weight_oz,dest_postal\n"
            "1Z999AA10123456784,ups,3000,60614\n"
        )
        code, output = self._run([], stdin_text=csv_text)
        self.assertEqual(code, 0)
        self.assertIn("W020", output)

    def test_reads_from_file_path(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, newline=""
        ) as f:
            f.write(
                "tracking_number,carrier,weight_oz,dest_postal\n"
                "1Z999AA10123456784,ups,32,60614\n"
            )
            path = f.name
        try:
            code, output = self._run([path])
            self.assertEqual(code, 0)
            self.assertEqual(output, "")
        finally:
            os.unlink(path)

    def test_error_message_includes_source_path(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, newline=""
        ) as f:
            f.write(
                "tracking_number,carrier,weight_oz,dest_postal\n,ups,32,60614\n"
            )
            path = f.name
        try:
            code, output = self._run([path])
            self.assertEqual(code, 1)
            self.assertIn(f"{path}:2:", output)
        finally:
            os.unlink(path)

    def test_json_format_clean_manifest(self):
        csv_text = (
            "tracking_number,carrier,weight_oz,dest_postal\n"
            "1Z999AA10123456784,ups,32,60614\n"
        )
        code, output = self._run(["--format", "json"], stdin_text=csv_text)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output), [])

    def test_json_format_reports_findings(self):
        csv_text = (
            "tracking_number,carrier,weight_oz,dest_postal\n,ups,32,60614\n"
        )
        code, output = self._run(["--format", "json"], stdin_text=csv_text)
        self.assertEqual(code, 1)
        findings = json.loads(output)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["code"], "E010")
        self.assertEqual(findings[0]["level"], "error")
        self.assertEqual(findings[0]["line"], 2)
        self.assertEqual(findings[0]["source"], "<stdin>")

    def test_json_format_is_single_line_output(self):
        csv_text = (
            "tracking_number,carrier,weight_oz,dest_postal\n"
            ",ups,32,60614\n"
            "1Z999AA10123456784,ups,heavy,60614\n"
        )
        code, output = self._run(["--format", "json"], stdin_text=csv_text)
        self.assertEqual(code, 1)
        self.assertEqual(output.count("\n"), 1)
        findings = json.loads(output)
        self.assertEqual([f["code"] for f in findings], ["E010", "E021"])


if __name__ == "__main__":
    unittest.main()
