import unittest
from core.reasoning.missing_dimension import MissingDimensionGenerator

class TestMissingDimensionGenerator(unittest.TestCase):
    def setUp(self):
        self.generator = MissingDimensionGenerator()

    def test_pocket_loop_x_axis(self):
        # Overall width = 200, perimeter wall = 10, pocket length = 180
        # 180 + 2 * 10 = 200. Mathematically correct.
        semantic_record = {
            "drawing_id": "test_drawing",
            "part_type": "mechanical_component",
            "overall_dimensions": {"width": 200.0, "height": 100.0},
            "features": [
                {
                    "feature_id": "pocket_1",
                    "feature_class": "pocket",
                    "parameters": {
                        "pocket_length": 180.0,
                        "pocket_width": 80.0,
                        "perimeter_wall": 10.0
                    }
                }
            ],
            "relationships": [],
            "metadata": {}
        }
        
        tasks = self.generator.generate(semantic_record, {"entities": []})
        # Should generate pocket tasks for X and Y axis loops
        self.assertTrue(len(tasks) > 0)
        
        # Verify pocket_length masked task properties
        pocket_len_tasks = [t for t in tasks if t["target"]["property"] == "pocket_length"]
        self.assertEqual(len(pocket_len_tasks), 1)
        t = pocket_len_tasks[0]
        self.assertEqual(t["target"]["value"], 180.0)
        self.assertEqual(t["context"]["inquiry_feature"]["visible_parameters"]["pocket_length"], None)
        self.assertEqual(t["context"]["inquiry_feature"]["visible_parameters"]["perimeter_wall"], 10.0)
        self.assertIn("pocket_length = width - 2 * perimeter_wall", t["reasoning_metadata"]["formula"])

    def test_concentric_bore_loop(self):
        semantic_record = {
            "drawing_id": "test_concentric",
            "part_type": "mechanical_component",
            "overall_dimensions": {"width": 100.0, "height": 100.0},
            "features": [
                {
                    "feature_id": "bore_1",
                    "feature_class": "concentric_bore",
                    "parameters": {
                        "inner_diameter": 40.0,
                        "outer_diameter": 100.0
                    }
                }
            ],
            "relationships": [],
            "metadata": {}
        }
        
        tasks = self.generator.generate(semantic_record, {"entities": []})
        self.assertTrue(len(tasks) > 0)
        
        inner_tasks = [t for t in tasks if t["target"]["property"] == "inner_diameter"]
        self.assertEqual(len(inner_tasks), 1)
        t = inner_tasks[0]
        self.assertEqual(t["target"]["value"], 40.0)
        self.assertEqual(t["context"]["inquiry_feature"]["visible_parameters"]["outer_diameter"], 100.0)
        self.assertEqual(t["context"]["inquiry_feature"]["visible_parameters"]["wall_thickness"], 30.0)

    def test_pattern_spacing_loop(self):
        semantic_record = {
            "drawing_id": "test_pattern",
            "part_type": "mechanical_component",
            "overall_dimensions": {"width": 300.0, "height": 100.0},
            "features": [
                {
                    "feature_id": "hg_1",
                    "feature_class": "hole_group",
                    "parameters": {
                        "count": 3,
                        "spacing_x": 100.0
                    }
                }
            ],
            "relationships": [],
            "metadata": {}
        }
        
        tasks = self.generator.generate(semantic_record, {"entities": []})
        self.assertTrue(len(tasks) > 0)
        
        spacing_tasks = [t for t in tasks if t["target"]["property"] == "spacing"]
        self.assertEqual(len(spacing_tasks), 1)
        t = spacing_tasks[0]
        self.assertEqual(t["target"]["value"], 100.0)
        self.assertEqual(t["context"]["inquiry_feature"]["visible_parameters"]["count"], 3)
        self.assertEqual(t["context"]["inquiry_feature"]["visible_parameters"]["feature_span"], 200.0)

    def test_leakage_prevention(self):
        # If prompt contains the target value (e.g. coincidental match), task should be discarded.
        # Here we manually simulate leakage checking
        has_leak = self.generator._detect_leakage(180.0, "The pocket length is 180.0 mm.")
        self.assertTrue(has_leak)
        
        has_no_leak = self.generator._detect_leakage(180.0, "The pocket length is masked.")
        self.assertFalse(has_no_leak)

    def test_relationship_target_property_is_masked(self):
        relationships = [{
            "relationship_type": "concentric",
            "parameters": {"inner_diameter": 40.0, "outer_diameter": 80.0},
        }]

        masked = self.generator._mask_target_relationship_values(relationships, "inner_diameter")

        self.assertIsNone(masked[0]["parameters"]["inner_diameter"])
        self.assertEqual(masked[0]["parameters"]["outer_diameter"], 80.0)
        self.assertEqual(relationships[0]["parameters"]["inner_diameter"], 40.0)

if __name__ == "__main__":
    unittest.main()
