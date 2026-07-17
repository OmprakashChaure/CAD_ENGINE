"""
Bug Condition Exploration Test for Phase-7 Arithmetic Leakage

**CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists.
DO NOT attempt to fix the test or the code when it fails.

This test surfaces counterexamples demonstrating arithmetic leakage:
- Tasks solvable by trivial arithmetic (distance calculation, aspect ratio, counting)
- Missing engineering context (relationships, hierarchy)
- Complete data instead of partial data

Expected counterexamples:
1. Radial task includes all 4 hole positions → solvable by distance calculation
2. Slot task includes aspect_ratio → solvable by arithmetic (width = length / aspect_ratio)
3. Concentric task lacks relationships → solvable by radius extraction
4. Tasks lack relationships field (no concentric_with, symmetric_to)
5. Tasks lack hierarchy field (no parent_feature, nesting_depth)

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7**
"""
import math
import pytest
from pipeline.dataset_pipeline import DatasetExporter


class TestPhase7ArithmeticLeakage:
    """
    Bug Condition Exploration: Detect arithmetic leakage in Phase-7 export.
    
    These tests target concrete failing cases with known feature patterns.
    Each test attempts to solve the exported task using ONLY trivial arithmetic.
    If solvable by arithmetic → task demonstrates the bug.
    """

    def test_radial_pattern_arithmetic_leakage(self):
        """
        Test Case 1: Radial Pattern with Complete Hole Positions
        
        Bug Condition: Exported task includes complete holes array (all 4 positions)
        Arithmetic Solution: Calculate distance from pattern center to any hole, multiply by 2 → PCD
        
        Expected Failure: Task provides complete data enabling distance calculation
        """
        # Arrange: Create pipeline output with radial pattern (4 holes, PCD=100)
        pipeline_output = self._create_radial_pattern_output(
            hole_count=4,
            pcd=100,
            hole_diameter=12,
            pattern_center=[60, 60]
        )
        
        # Act: Export tasks using current (unfixed) DatasetExporter
        exporter = DatasetExporter(output_dir="test_output")
        tasks = exporter._build_tasks(
            result=pipeline_output,
            drawing_id="test_radial"
        )
        
        # Find radial pattern task
        radial_tasks = [t for t in tasks if t.get("task_type") == "infer_pitch_circle_diameter"]
        assert len(radial_tasks) > 0, "No radial pattern tasks generated"
        
        task = radial_tasks[0]
        context = task["context"]
        target = task["target"]
        
        # Assert 1: Task should NOT include complete holes array (EXPECTED TO FAIL)
        holes = context.get("holes", [])
        hole_count = context.get("hole_count", len(holes))
        
        assert len(holes) < hole_count, (
            f"ARITHMETIC LEAKAGE DETECTED: Task includes complete holes array "
            f"({len(holes)} of {hole_count} holes). This enables trivial distance calculation. "
            f"Expected: partial holes (e.g., 2 of 4) to force engineering reasoning."
        )
        
        # Assert 2: Task should include relationships (EXPECTED TO FAIL)
        relationships = context.get("relationships", [])
        assert len(relationships) > 0, (
            f"MISSING ENGINEERING CONTEXT: Task lacks relationships field. "
            f"Expected: concentric_with outer flange, symmetric relationships, etc."
        )
        
        # Assert 3: Task should include hierarchy (EXPECTED TO FAIL)
        hierarchy = context.get("hierarchy")
        assert hierarchy is not None, (
            f"MISSING ENGINEERING CONTEXT: Task lacks hierarchy field. "
            f"Expected: parent_feature, nesting_depth, child_features."
        )
        
        # Assert 4: Verify task CANNOT be solved by arithmetic alone
        # If we can calculate PCD from complete holes array, the task has arithmetic leakage
        if len(holes) == hole_count and len(holes) >= 2:
            # Arithmetic solution: distance from center to first hole * 2
            center = context.get("pattern_center", [0, 0])
            first_hole = holes[0]["center"]
            dx = first_hole[0] - center[0]
            dy = first_hole[1] - center[1]
            calculated_pcd = round(math.sqrt(dx**2 + dy**2) * 2, 4)
            expected_pcd = target["value"]
            
            # If arithmetic solution matches target, task has leakage
            assert abs(calculated_pcd - expected_pcd) > 0.1, (
                f"ARITHMETIC LEAKAGE CONFIRMED: Task is solvable by distance calculation. "
                f"Calculated PCD from complete holes: {calculated_pcd}, Target: {expected_pcd}. "
                f"This requires NO engineering reasoning."
            )

    def test_slot_aspect_ratio_arithmetic_leakage(self):
        """
        Test Case 2: Slot Task with Aspect Ratio Visible
        
        Bug Condition: Exported task includes aspect_ratio in context
        Arithmetic Solution: width = length / aspect_ratio
        
        Expected Failure: Task provides aspect_ratio enabling arithmetic shortcut
        """
        # Arrange: Create pipeline output with slot (length=294, width=28, aspect_ratio=10.5)
        pipeline_output = self._create_slot_output(
            length=294,
            width=28,
            aspect_ratio=10.5,
            center=[100, 100]
        )
        
        # Act: Export tasks
        exporter = DatasetExporter(output_dir="test_output")
        tasks = exporter._build_tasks(
            result=pipeline_output,
            drawing_id="test_slot"
        )
        
        # Find slot task
        slot_tasks = [t for t in tasks if t.get("task_type") == "infer_slot_width"]
        assert len(slot_tasks) > 0, "No slot tasks generated"
        
        task = slot_tasks[0]
        context = task["context"]
        target = task["target"]
        
        # Assert 1: Task should NOT include aspect_ratio (EXPECTED TO FAIL)
        aspect_ratio = context.get("aspect_ratio")
        assert aspect_ratio is None, (
            f"ARITHMETIC LEAKAGE DETECTED: Task includes aspect_ratio={aspect_ratio}. "
            f"This enables trivial arithmetic: width = length / aspect_ratio. "
            f"Expected: aspect_ratio removed to force engineering reasoning."
        )
        
        # Assert 2: Verify task CANNOT be solved by arithmetic
        if aspect_ratio is not None:
            slot_length = context.get("slot_length", 0)
            calculated_width = round(slot_length / aspect_ratio, 4)
            expected_width = target["value"]
            
            assert abs(calculated_width - expected_width) > 0.1, (
                f"ARITHMETIC LEAKAGE CONFIRMED: Task is solvable by arithmetic. "
                f"Calculated width: {calculated_width} = {slot_length} / {aspect_ratio}, "
                f"Target: {expected_width}. This requires NO engineering reasoning."
            )

    def test_concentric_missing_relationships(self):
        """
        Test Case 3: Concentric Task with Only 2 Circles, No Relationships
        
        Bug Condition: Exported task has only 2 circles and no relationships
        Arithmetic Solution: Extract radii from geometry, multiply by 2 → diameters
        
        Expected Failure: Task lacks relationships, solvable by radius extraction
        """
        # Arrange: Create pipeline output with concentric circles (radii: [20, 30, 50])
        pipeline_output = self._create_concentric_output(
            radii=[20, 30, 50],
            center=[100, 100]
        )
        
        # Act: Export tasks
        exporter = DatasetExporter(output_dir="test_output")
        tasks = exporter._build_tasks(
            result=pipeline_output,
            drawing_id="test_concentric"
        )
        
        # Find concentric task
        concentric_tasks = [t for t in tasks if t.get("task_type") == "infer_inner_diameter"]
        assert len(concentric_tasks) > 0, "No concentric tasks generated"
        
        task = concentric_tasks[0]
        context = task["context"]
        
        # Assert 1: Task should include relationships (EXPECTED TO FAIL)
        relationships = context.get("relationships", [])
        radius_count = context.get("radius_count", 0)
        
        if radius_count == 2:
            assert len(relationships) > 0, (
                f"ARITHMETIC LEAKAGE DETECTED: Task has only 2 circles and no relationships. "
                f"This enables trivial radius extraction from geometry. "
                f"Expected: relationships (concentric_with features) to force engineering reasoning."
            )
        
        # Assert 2: Task should include hierarchy (EXPECTED TO FAIL)
        hierarchy = context.get("hierarchy")
        assert hierarchy is not None, (
            f"MISSING ENGINEERING CONTEXT: Task lacks hierarchy field. "
            f"Expected: parent_feature (flange), nesting_depth, child_features (bore)."
        )

    def test_repetition_complete_positions_arithmetic_leakage(self):
        """
        Test Case 4: Repetition Task with Complete Positions Array
        
        Bug Condition: Exported task includes all feature positions
        Arithmetic Solution: spacing = distance(pos[0], pos[1])
        
        Expected Failure: Task provides complete positions enabling trivial spacing calculation
        """
        # Arrange: Create pipeline output with repeated features (7 slots)
        pipeline_output = self._create_repetition_output(
            feature_count=7,
            spacing=295.5,
            feature_diameter=28
        )
        
        # Act: Export tasks
        exporter = DatasetExporter(output_dir="test_output")
        tasks = exporter._build_tasks(
            result=pipeline_output,
            drawing_id="test_repetition"
        )
        
        # Find repetition task (task type changed from infer_repeated_feature_count to infer_repeated_feature_spacing)
        repetition_tasks = [t for t in tasks if t.get("task_type") == "infer_repeated_feature_spacing"]
        assert len(repetition_tasks) > 0, "No repetition tasks generated"
        
        task = repetition_tasks[0]
        context = task["context"]
        target = task["target"]
        
        # Assert 1: Task should NOT include complete positions (EXPECTED TO FAIL)
        known_positions = context.get("known_positions", [])
        total_count = context.get("total_feature_count", 0)
        
        assert len(known_positions) < total_count, (
            f"ARITHMETIC LEAKAGE DETECTED: Task includes complete positions array "
            f"({len(known_positions)} of {total_count} features). This enables trivial spacing calculation. "
            f"Expected: partial positions (e.g., 3 of 7) to force engineering reasoning."
        )

    # Helper methods to create test pipeline outputs

    def _create_radial_pattern_output(self, hole_count, pcd, hole_diameter, pattern_center):
        """Create pipeline output with radial pattern."""
        pattern_radius = pcd / 2
        angular_spacing = 360 / hole_count
        
        # Generate hole positions on circle
        holes = []
        hole_candidates = []
        entities = []
        
        for i in range(hole_count):
            angle_rad = math.radians(i * angular_spacing)
            x = pattern_center[0] + pattern_radius * math.cos(angle_rad)
            y = pattern_center[1] + pattern_radius * math.sin(angle_rad)
            
            entity_id = f"circle_{i}"
            entities.append({
                "entity_id": entity_id,
                "entity_type": "CIRCLE",
                "geometry": {
                    "center": [round(x, 4), round(y, 4)],
                    "diameter": hole_diameter
                }
            })
            
            candidate_id = f"hc_{i}"
            hole_candidates.append({
                "candidate_id": candidate_id,
                "entity_ids": [entity_id],
                "center": [round(x, 4), round(y, 4)],
                "diameter": hole_diameter
            })
        
        # Add concentric group for relationships
        concentric_groups = [{
            "group_id": "cg_001",
            "center": pattern_center,
            "radii": [pattern_radius, pattern_radius + 10],  # Pattern + outer flange
            "entity_ids": [f"circle_{i}" for i in range(hole_count)] + ["outer_flange"],
            "count": 2
        }]
        
        # Add contour hierarchy
        contour_hierarchy = {
            "hierarchy": [
                {
                    "entity_id": f"circle_{i}",
                    "parent_id": "outer_flange",
                    "nesting_depth": 1,
                    "children_ids": []
                }
                for i in range(hole_count)
            ] + [{
                "entity_id": "outer_flange",
                "parent_id": None,
                "nesting_depth": 0,
                "children_ids": [f"circle_{i}" for i in range(hole_count)]
            }]
        }
        
        # Add symmetry groups for relationships
        symmetry_groups = [{
            "axis": "horizontal",
            "axis_position": pattern_center[1],
            "member_pairs": [[f"hc_0", f"hc_2"], [f"hc_1", f"hc_3"]]
        }]
        
        return {
            "entities": entities,
            "feature_result": {
                "radial_patterns": {
                    "radial_patterns": [{
                        "pattern_id": "rp_001",
                        "center": pattern_center,
                        "pattern_radius": pattern_radius,
                        "member_candidate_ids": [hc["candidate_id"] for hc in hole_candidates],
                        "angular_spacing_deg": angular_spacing
                    }]
                },
                "hole_candidates": {
                    "hole_candidates": hole_candidates
                },
                "symmetry": {
                    "symmetry_groups": symmetry_groups
                }
            },
            "structural_result": {
                "concentric_groups": {"concentric_groups": concentric_groups},
                "contour_hierarchy": contour_hierarchy
            },
            "refinement_result": {
                "repetitions": {"repetition_groups": []}
            },
            "context_result": {
                "relationships": {"relationships": []},
                "symmetry": {"symmetry_groups": symmetry_groups}
            }
        }

    def _create_slot_output(self, length, width, aspect_ratio, center):
        """Create pipeline output with slot."""
        entity_id = "slot_001"
        candidate_id = "sc_001"
        
        return {
            "entities": [{
                "entity_id": entity_id,
                "entity_type": "POLYLINE",
                "geometry": {
                    "center": center,
                    "width": width,
                    "height": length
                }
            }],
            "feature_result": {
                "slot_candidates": {
                    "slot_candidates": [{
                        "candidate_id": candidate_id,
                        "entity_ids": [entity_id],
                        "center": center,
                        "width": width,
                        "height": length,
                        "aspect_ratio": aspect_ratio
                    }]
                },
                "radial_patterns": {"radial_patterns": []},
                "hole_candidates": {"hole_candidates": []}
            },
            "structural_result": {
                "concentric_groups": {"concentric_groups": []}
            },
            "refinement_result": {
                "repetitions": {"repetition_groups": []}
            }
        }

    def _create_concentric_output(self, radii, center):
        """Create pipeline output with concentric circles."""
        entities = []
        entity_ids = []
        
        for i, radius in enumerate(radii):
            entity_id = f"circle_{i}"
            entity_ids.append(entity_id)
            entities.append({
                "entity_id": entity_id,
                "entity_type": "CIRCLE",
                "geometry": {
                    "center": center,
                    "diameter": radius * 2
                }
            })
        
        # Add contour hierarchy for concentric system
        contour_hierarchy = {
            "hierarchy": [
                {
                    "entity_id": entity_ids[0],  # Inner circle
                    "parent_id": entity_ids[1],  # Middle circle
                    "nesting_depth": 2,
                    "children_ids": []
                },
                {
                    "entity_id": entity_ids[1],  # Middle circle
                    "parent_id": entity_ids[2],  # Outer circle
                    "nesting_depth": 1,
                    "children_ids": [entity_ids[0]]
                },
                {
                    "entity_id": entity_ids[2],  # Outer circle
                    "parent_id": None,
                    "nesting_depth": 0,
                    "children_ids": [entity_ids[1]]
                }
            ]
        }
        
        return {
            "entities": entities,
            "feature_result": {
                "radial_patterns": {"radial_patterns": []},
                "hole_candidates": {"hole_candidates": []},
                "slot_candidates": {"slot_candidates": []}
            },
            "structural_result": {
                "concentric_groups": {
                    "concentric_groups": [{
                        "group_id": "cg_001",
                        "center": center,
                        "radii": radii,
                        "entity_ids": entity_ids,
                        "count": len(radii)
                    }]
                },
                "contour_hierarchy": contour_hierarchy
            },
            "refinement_result": {
                "repetitions": {"repetition_groups": []}
            },
            "context_result": {
                "relationships": {"relationships": []}
            }
        }

    def _create_repetition_output(self, feature_count, spacing, feature_diameter):
        """Create pipeline output with repeated features."""
        entities = []
        hole_candidates = []
        candidate_ids = []
        
        base_x = 500
        base_y = 1711
        
        for i in range(feature_count):
            x = base_x + i * spacing
            entity_id = f"hole_{i}"
            candidate_id = f"hc_{i}"
            
            entities.append({
                "entity_id": entity_id,
                "entity_type": "CIRCLE",
                "geometry": {
                    "center": [round(x, 4), base_y],
                    "diameter": feature_diameter
                }
            })
            
            hole_candidates.append({
                "candidate_id": candidate_id,
                "entity_ids": [entity_id],
                "center": [round(x, 4), base_y],
                "diameter": feature_diameter
            })
            
            candidate_ids.append(candidate_id)
        
        return {
            "entities": entities,
            "feature_result": {
                "radial_patterns": {"radial_patterns": []},
                "hole_candidates": {
                    "hole_candidates": hole_candidates
                },
                "slot_candidates": {"slot_candidates": []}
            },
            "structural_result": {
                "concentric_groups": {"concentric_groups": []}
            },
            "refinement_result": {
                "repetitions": {
                    "repetition_groups": [{
                        "group_id": "rg_001",
                        "candidate_ids": candidate_ids,
                        "signature": f"CIRCLE_d{feature_diameter}",
                        "repetition_count": feature_count
                    }]
                }
            }
        }
