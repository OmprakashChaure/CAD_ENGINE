import unittest
from pipeline.semantic_pipeline import map_features, extract_dimension_facts


class TestSemanticIntegration(unittest.TestCase):
    def test_semantic_dimension_facts_extraction(self):
        # Create dummy entities with raw annotations
        entities = [
            {
                "entity_id": 1,
                "entity_type": "TEXT",
                "geometry": {
                    "text": "6X M8X1.25 TERMINAL BORE",
                    "value": None,
                    "target_points": [[0.0, 0.0], [1.0, 1.0]],
                },
                "handle": "H1",
            },
            {
                "entity_id": 2,
                "entity_type": "TEXT",
                "geometry": {
                    "text": "PCBORE Ø20MM X 10MM DEEP",
                    "value": None,
                    "target_points": [[0.0, 0.0], [1.0, 1.0]],
                },
                "handle": "H2",
            },
            {
                "entity_id": 3,
                "entity_type": "TEXT",
                "geometry": {
                    "text": "CHAMFER 2MM X 45 DEG",
                    "value": 2.0,
                    "target_points": [[0.0, 0.0], [1.0, 1.0]],
                },
                "handle": "H3",
            },
            {
                "entity_id": 4,
                "entity_type": "DIMENSION",
                "geometry": {
                    "text": "50H7",
                    "value": 50.0,
                    "target_points": [[0.0, 0.0], [1.0, 1.0]],
                },
                "handle": "H4",
            },
        ]

        facts = extract_dimension_facts(entities)

        # Verify counterbore facts populated via parser
        self.assertIsNotNone(facts.get("counterbore"))
        self.assertEqual(
            facts["counterbore"]["counterbore_diameter"], 20.0
        )
        self.assertEqual(facts["counterbore"]["counterbore_depth"], 10.0)

        # Verify hole callouts populated via thread parser
        self.assertEqual(len(facts.get("hole_callouts")), 1)
        self.assertEqual(facts["hole_callouts"][0]["count"], 6)
        self.assertEqual(facts["hole_callouts"][0]["diameter"], 8.0)

    def test_semantic_feature_mapping(self):
        # Entities for a thread feature
        entities = [
            {
                "entity_id": 1,
                "entity_type": "MTEXT",
                "geometry": {
                    "text": "M12X1.75-6G INTERNAL THREAD",
                    "value": None,
                    "target_points": [[0.0, 0.0], [0.0, 10.0]],
                },
                "handle": "H1",
            }
        ]

        # Dummy structural and feature phase results
        phase3_result = {}
        phase4_result = {}
        phase5_result = {}

        features, _ = map_features(
            entities, phase3_result, phase4_result, phase5_result
        )

        # Find the thread feature
        thread_feats = [f for f in features if f.feature_class == "thread"]
        self.assertEqual(len(thread_feats), 1)

        # Verify structured attributes exist in the parameters dict
        params = thread_feats[0].parameters
        self.assertEqual(params["thread_standard"], "ISO Metric")
        self.assertEqual(params["nominal_diameter"], 12.0)
        self.assertEqual(params["thread_pitch"], 1.75)
        self.assertEqual(params["thread_gender"], "internal")
        self.assertEqual(params["tolerance_class"], "6G")
        self.assertEqual(params["validation_status"], "validated")
        self.assertEqual(
            params["source_annotation"], "M12X1.75-6G INTERNAL THREAD"
        )

        # Verify backward compatibility legacy keys remain
        self.assertEqual(
            params["thread_designation"], "M12X1.75-6G INTERNAL THREAD"
        )
        self.assertEqual(params["pitch"], 1.75)


if __name__ == "__main__":
    unittest.main()
