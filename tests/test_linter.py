import unittest
from io import StringIO

from shiplabel_lint.linter import lint_stream


def lint(text):
    return list(lint_stream(StringIO(text)))


class TestLintStream(unittest.TestCase):
    def test_empty_input(self):
        findings = lint("")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "E000")

    def test_missing_required_column(self):
        findings = lint("tracking_number,carrier,weight_oz\n1Z999AA10123456784,ups,32\n")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "E001")
        self.assertIn("dest_postal", findings[0].message)

    def test_clean_row_has_no_findings(self):
        findings = lint(
            "tracking_number,carrier,weight_oz,dest_postal\n"
            "1Z999AA10123456784,ups,32,60614\n"
        )
        self.assertEqual(findings, [])

    def test_missing_tracking_number(self):
        findings = lint(
            "tracking_number,carrier,weight_oz,dest_postal\n,ups,32,60614\n"
        )
        self.assertIn("E010", [f.code for f in findings])

    def test_tracking_number_wrong_format(self):
        findings = lint(
            "tracking_number,carrier,weight_oz,dest_postal\n123,fedex,32,60614\n"
        )
        self.assertIn("E011", [f.code for f in findings])

    def test_duplicate_tracking_number(self):
        findings = lint(
            "tracking_number,carrier,weight_oz,dest_postal\n"
            "1Z999AA10123456784,ups,32,60614\n"
            "1Z999AA10123456784,ups,20,90210\n"
        )
        dup = [f for f in findings if f.code == "E012"]
        self.assertEqual(len(dup), 1)
        self.assertEqual(dup[0].line, 3)

    def test_unknown_carrier_warns_but_does_not_check_format(self):
        findings = lint(
            "tracking_number,carrier,weight_oz,dest_postal\nABC123,ontrac,32,60614\n"
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "W010")
        self.assertEqual(findings[0].level, "warning")

    def test_missing_weight(self):
        findings = lint(
            "tracking_number,carrier,weight_oz,dest_postal\n1Z999AA10123456784,ups,,60614\n"
        )
        self.assertIn("E020", [f.code for f in findings])

    def test_weight_not_a_number(self):
        findings = lint(
            "tracking_number,carrier,weight_oz,dest_postal\n"
            "1Z999AA10123456784,ups,heavy,60614\n"
        )
        self.assertIn("E021", [f.code for f in findings])

    def test_weight_zero(self):
        findings = lint(
            "tracking_number,carrier,weight_oz,dest_postal\n1Z999AA10123456784,ups,0,60614\n"
        )
        self.assertIn("E022", [f.code for f in findings])

    def test_weight_negative(self):
        findings = lint(
            "tracking_number,carrier,weight_oz,dest_postal\n"
            "1Z999AA10123456784,ups,-5,60614\n"
        )
        self.assertIn("E022", [f.code for f in findings])

    def test_weight_over_limit_is_warning_not_error(self):
        findings = lint(
            "tracking_number,carrier,weight_oz,dest_postal\n"
            "1Z999AA10123456784,ups,3000,60614\n"
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "W020")
        self.assertEqual(findings[0].level, "warning")

    def test_missing_postal(self):
        findings = lint(
            "tracking_number,carrier,weight_oz,dest_postal\n1Z999AA10123456784,ups,32,\n"
        )
        self.assertIn("E030", [f.code for f in findings])

    def test_invalid_postal(self):
        findings = lint(
            "tracking_number,carrier,weight_oz,dest_postal\n"
            "1Z999AA10123456784,ups,32,not-a-zip\n"
        )
        self.assertIn("E031", [f.code for f in findings])

    def test_canadian_postal_code_accepted(self):
        findings = lint(
            "tracking_number,carrier,weight_oz,dest_postal\n"
            "1Z999AA10123456784,ups,32,K1A 0B1\n"
        )
        self.assertEqual(findings, [])

    def test_us_zip_plus_four_accepted(self):
        findings = lint(
            "tracking_number,carrier,weight_oz,dest_postal\n"
            "1Z999AA10123456784,ups,32,60614-1234\n"
        )
        self.assertEqual(findings, [])

    def test_blank_rows_are_skipped(self):
        findings = lint(
            "tracking_number,carrier,weight_oz,dest_postal\n"
            "\n"
            "1Z999AA10123456784,ups,32,60614\n"
        )
        self.assertEqual(findings, [])

    def test_line_numbers_account_for_header(self):
        findings = lint(
            "tracking_number,carrier,weight_oz,dest_postal\n"
            "1Z999AA10123456784,ups,32,60614\n"
            ",ups,32,60614\n"
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].line, 3)

    def test_header_lookup_is_case_insensitive(self):
        findings = lint(
            "Tracking_Number,Carrier,Weight_OZ,Dest_Postal\n"
            "1Z999AA10123456784,ups,32,60614\n"
        )
        self.assertEqual(findings, [])

    def test_short_row_treated_as_missing_trailing_fields(self):
        findings = lint(
            "tracking_number,carrier,weight_oz,dest_postal\n1Z999AA10123456784,ups\n"
        )
        codes = [f.code for f in findings]
        self.assertIn("E020", codes)
        self.assertIn("E030", codes)

    def test_manifest_without_dimension_columns_is_unaffected(self):
        findings = lint(
            "tracking_number,carrier,weight_oz,dest_postal\n"
            "1Z999AA10123456784,ups,32,60614\n"
        )
        self.assertEqual(findings, [])

    def test_row_with_blank_dimensions_is_unaffected(self):
        findings = lint(
            "tracking_number,carrier,weight_oz,length_in,width_in,height_in,dest_postal\n"
            "1Z999AA10123456784,ups,32,,,,60614\n"
        )
        self.assertEqual(findings, [])

    def test_partial_dimensions_is_an_error(self):
        findings = lint(
            "tracking_number,carrier,weight_oz,length_in,width_in,height_in,dest_postal\n"
            "1Z999AA10123456784,ups,32,12,9,,60614\n"
        )
        self.assertIn("E023", [f.code for f in findings])

    def test_dimension_not_a_number(self):
        findings = lint(
            "tracking_number,carrier,weight_oz,length_in,width_in,height_in,dest_postal\n"
            "1Z999AA10123456784,ups,32,big,9,4,60614\n"
        )
        self.assertIn("E024", [f.code for f in findings])

    def test_dimension_zero_or_negative(self):
        findings = lint(
            "tracking_number,carrier,weight_oz,length_in,width_in,height_in,dest_postal\n"
            "1Z999AA10123456784,ups,32,0,9,4,60614\n"
        )
        self.assertIn("E025", [f.code for f in findings])

    def test_oversize_package_warns(self):
        findings = lint(
            "tracking_number,carrier,weight_oz,length_in,width_in,height_in,dest_postal\n"
            "1Z999AA10123456784,ups,320,60,30,30,60614\n"
        )
        oversize = [f for f in findings if f.code == "W030"]
        self.assertEqual(len(oversize), 1)
        self.assertEqual(oversize[0].level, "warning")

    def test_dimensional_weight_exceeding_actual_weight_warns(self):
        findings = lint(
            "tracking_number,carrier,weight_oz,length_in,width_in,height_in,dest_postal\n"
            "1Z999AA10123456784,ups,10,12,9,4,60614\n"
        )
        dim_weight = [f for f in findings if f.code == "W031"]
        self.assertEqual(len(dim_weight), 1)
        self.assertEqual(dim_weight[0].level, "warning")

    def test_dimensional_weight_under_actual_weight_is_silent(self):
        findings = lint(
            "tracking_number,carrier,weight_oz,length_in,width_in,height_in,dest_postal\n"
            "1Z999AA10123456784,ups,200,12,9,4,60614\n"
        )
        self.assertEqual(findings, [])

    def test_small_package_is_not_flagged_as_dimensions(self):
        findings = lint(
            "tracking_number,carrier,weight_oz,length_in,width_in,height_in,dest_postal\n"
            "1Z999AA10123456784,ups,10,6,4,2,60614\n"
        )
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
