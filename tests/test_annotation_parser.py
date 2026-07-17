import unittest
from core.semantics.annotation_parser import AnnotationParser


class TestAnnotationParser(unittest.TestCase):
    def setUp(self):
        self.parser = AnnotationParser()

    def test_normalize(self):
        self.assertEqual(self.parser.normalize("  m12  "), "M12")
        self.assertEqual(
            self.parser.normalize("m12\\Pinternal"), "M12 INTERNAL"
        )
        self.assertEqual(self.parser.normalize("%%c20"), "Ø20")
        self.assertEqual(self.parser.normalize(None), "")

    def test_metric_thread_parsing(self):
        # Full metric thread
        parsed = self.parser.parse("M12X1.75-6g")
        self.assertEqual(parsed.annotation_type, "thread")
        self.assertEqual(parsed.thread_standard, "ISO Metric")
        self.assertEqual(parsed.nominal_diameter, 12.0)
        self.assertEqual(parsed.thread_pitch, 1.75)
        self.assertEqual(parsed.tolerance_class, "6G")
        self.assertEqual(parsed.validation_status, "validated")

        # Coarse fallback thread
        parsed_coarse = self.parser.parse("M10")
        self.assertEqual(parsed_coarse.annotation_type, "thread")
        self.assertEqual(parsed_coarse.nominal_diameter, 10.0)
        self.assertEqual(parsed_coarse.thread_pitch, 1.5)
        self.assertEqual(parsed_coarse.validation_status, "fallback")

        # Quantity metric thread
        parsed_qty = self.parser.parse("6X M8X1.25 TERMINAL BORE")
        self.assertEqual(parsed_qty.annotation_type, "thread")
        self.assertEqual(parsed_qty.quantity, 6)
        self.assertEqual(parsed_qty.nominal_diameter, 8.0)
        self.assertEqual(parsed_qty.thread_pitch, 1.25)
        self.assertEqual(parsed_qty.role, "TERMINAL BORE")
        self.assertEqual(parsed_qty.validation_status, "validated")

    def test_unified_thread_parsing(self):
        # UNC
        parsed = self.parser.parse("1/2-13 UNC")
        self.assertEqual(parsed.annotation_type, "thread")
        self.assertEqual(parsed.thread_standard, "UNC")
        self.assertEqual(parsed.nominal_pipe_size, "1/2")
        self.assertEqual(parsed.pitch_tpi, 13)
        self.assertEqual(parsed.nominal_diameter, 12.7)  # 0.5 * 25.4
        self.assertEqual(parsed.validation_status, "validated")

        # UNF
        parsed_unf = self.parser.parse("3/8-24 UNF")
        self.assertEqual(parsed_unf.annotation_type, "thread")
        self.assertEqual(parsed_unf.thread_standard, "UNF")
        self.assertEqual(parsed_unf.pitch_tpi, 24)
        self.assertEqual(parsed_unf.validation_status, "validated")

    def test_pipe_thread_parsing(self):
        # BSPP G
        parsed_g = self.parser.parse("G1/4 BSPP")
        self.assertEqual(parsed_g.annotation_type, "thread")
        self.assertEqual(parsed_g.thread_standard, "BSPP")
        self.assertEqual(parsed_g.nominal_pipe_size, "1/4")
        self.assertEqual(parsed_g.nominal_diameter, 13.157)
        self.assertEqual(parsed_g.validation_status, "validated")

        # NPT
        parsed_npt = self.parser.parse("NPT1/2")
        self.assertEqual(parsed_npt.annotation_type, "thread")
        self.assertEqual(parsed_npt.thread_standard, "NPT")
        self.assertEqual(parsed_npt.nominal_pipe_size, "1/2")
        self.assertEqual(parsed_npt.nominal_diameter, 21.336)
        self.assertEqual(parsed_npt.taper, 0.0625)
        self.assertEqual(parsed_npt.validation_status, "validated")

    def test_counterbore_parsing(self):
        parsed = self.parser.parse("PCBORE Ø20MM X 10MM DEEP")
        self.assertEqual(parsed.annotation_type, "counterbore")
        self.assertEqual(parsed.counterbore_diameter, 20.0)
        self.assertEqual(parsed.counterbore_depth, 10.0)

        parsed_cb = self.parser.parse("CBORE Ø15 X 8")
        self.assertEqual(parsed_cb.annotation_type, "counterbore")
        self.assertEqual(parsed_cb.counterbore_diameter, 15.0)
        self.assertEqual(parsed_cb.counterbore_depth, 8.0)

    def test_chamfer_parsing(self):
        parsed = self.parser.parse("CHAMFER 2MM X 45 DEG")
        self.assertEqual(parsed.annotation_type, "chamfer")
        self.assertEqual(parsed.chamfer_size, 2.0)
        self.assertEqual(parsed.chamfer_angle, 45.0)

        parsed_short = self.parser.parse("CHAMFER 3")
        self.assertEqual(parsed_short.annotation_type, "chamfer")
        self.assertEqual(parsed_short.chamfer_size, 3.0)
        self.assertEqual(parsed_short.chamfer_angle, 45.0)  # Default angle

    def test_radius_parsing(self):
        parsed = self.parser.parse("R10")
        self.assertEqual(parsed.annotation_type, "radius")
        self.assertEqual(parsed.radius_value, 10.0)

        parsed_rad = self.parser.parse("RADIUS 15")
        self.assertEqual(parsed_rad.annotation_type, "radius")
        self.assertEqual(parsed_rad.radius_value, 15.0)

    def test_tolerance_parsing(self):
        parsed = self.parser.parse("±0.05")
        self.assertEqual(parsed.annotation_type, "tolerance")
        self.assertEqual(parsed.tolerance_upper, 0.05)
        self.assertEqual(parsed.tolerance_lower, -0.05)

        parsed_split = self.parser.parse("+0.02 / -0.01")
        self.assertEqual(parsed_split.annotation_type, "tolerance")
        self.assertEqual(parsed_split.tolerance_upper, 0.02)
        self.assertEqual(parsed_split.tolerance_lower, -0.01)

    def test_fit_parsing(self):
        # 50H7
        parsed = self.parser.parse("50H7")
        self.assertEqual(parsed.annotation_type, "fit")
        self.assertEqual(parsed.fit_class, "H7")
        self.assertEqual(parsed.nominal_diameter, 50.0)
        self.assertEqual(parsed.lower_deviation, 0.0)
        self.assertEqual(parsed.upper_deviation, 0.025)
        self.assertEqual(parsed.validation_status, "validated")

    def test_chamfer_bevel_validation(self):
        # Chamfer with quantity and angle
        parsed = self.parser.parse("2X CHAMFER 2MM X 45 DEG")
        self.assertEqual(parsed.annotation_type, "chamfer")
        self.assertEqual(parsed.chamfer_size, 2.0)
        self.assertEqual(parsed.chamfer_angle, 45.0)
        self.assertEqual(parsed.quantity, 2)
        
        # Chamfer without quantity
        parsed_no_qty = self.parser.parse("CHAMFER 3.5")
        self.assertEqual(parsed_no_qty.annotation_type, "chamfer")
        self.assertEqual(parsed_no_qty.chamfer_size, 3.5)
        self.assertEqual(parsed_no_qty.chamfer_angle, 45.0)
        self.assertIsNone(parsed_no_qty.quantity)
        
        # Bevel / unknown type parsing fallback
        parsed_bevel = self.parser.parse("3X BEVEL 2")
        self.assertEqual(parsed_bevel.annotation_type, "unknown")
        self.assertEqual(parsed_bevel.quantity, 3)

        # Malformed chamfer
        parsed_malformed = self.parser.parse("CHAMFER ABC")
        self.assertEqual(parsed_malformed.annotation_type, "unknown")
        self.assertIsNone(parsed_malformed.quantity)

    def test_invalid_and_unknown_parsing(self):
        parsed = self.parser.parse("INVALID_SPECIFICATION_999")
        self.assertEqual(parsed.annotation_type, "unknown")
        self.assertEqual(parsed.validation_status, "unvalidated")


if __name__ == "__main__":
    unittest.main()
