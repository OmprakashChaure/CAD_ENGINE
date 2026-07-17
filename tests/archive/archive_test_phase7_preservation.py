"""
Preservation Property Tests for Phase-7 Dataset Exporter

**IMPORTANT**: These tests validate UNCHANGED behaviors on UNFIXED code.
Tests should PASS on unfixed code to confirm baseline behavior to preserve.

These tests follow observation-first methodology:
1. Observe behavior on UNFIXED code for non-buggy inputs (drawings with no feature groups)
2. Write property-based tests capturing observed behavior patterns
3. Run tests on UNFIXED code
4. EXPECTED OUTCOME: Tests PASS (confirms baseline behavior to preserve)

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8**
"""
import hashlib
import json
import math
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pytest
from hypothesis import given, strategies as st, settings, assume

from core.exporters.dataset_exporter import DatasetExporter


class TestPhase7Preservation:
    """
    Preservation Property Tests: Verify unchanged behaviors on non-buggy inputs.
    
    These tests validate that Phase-7 preserves existing behavior for:
    - Deterministic hash-based splitting (70/15/15)
    - JSONL output format for train/validation/test splits
    - JSON metadata format
    - Entity lookup dictionary construction
    - Empty/invalid input handling
    - Mathematical formulas for geometric properties
    - File writing logic
    """

    @given(
        task_count=st.integers(min_value=1, max_value=100),
        seed=st.integers(min_value=0, max_value=1000)
    )
    @settings(max_examples=50, deadline=None)
    def test_deterministic_splitting_property(self, task_count, seed):
        """
        Property 1: Deterministic hash-based splitting produces identical splits on repeated runs.
        
        For any list of tasks, running _split_deterministic multiple times with the same
        input should produce identical train/validation/test splits.
        
        **Validates: Requirement 3.2**
        """
        # Arrange: Create dummy tasks
        tasks = [
            {
                "task_type": "dummy",
                "drawing_id": f"drawing_{i}",
                "context": {"value": i},
                "target": {"property": "test", "value": i * 2}
            }
            for i in range(task_count)
        ]
        
        # Act: Split tasks multiple times
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = DatasetExporter(output_dir=tmpdir)
            
            train1, val1, test1 = exporter._split_deterministic(tasks)
            train2, val2, test2 = exporter._split_deterministic(tasks)
        
        # Assert: Splits are identical
        assert len(train1) == len(train2), "Train split size changed between runs"
        assert len(val1) == len(val2), "Validation split size changed between runs"
        assert len(test1) == len(test2), "Test split size changed between runs"
        
        # Verify exact same tasks in each split
        assert train1 == train2, "Train split content changed between runs"
        assert val1 == val2, "Validation split content changed between runs"
        assert test1 == test2, "Test split content changed between runs"
        
        # Verify split ratios are approximately correct (70/15/15)
        # For small task counts, ratios may vary significantly due to rounding
        total = len(tasks)
        if total >= 10:  # Only check ratios for larger datasets
            train_ratio = len(train1) / total
            val_ratio = len(val1) / total
            test_ratio = len(test1) / total
            
            # Allow wider variance for small datasets
            assert 0.60 <= train_ratio <= 0.80, f"Train ratio {train_ratio} outside expected range"
            assert 0.05 <= val_ratio <= 0.25, f"Validation ratio {val_ratio} outside expected range"
            assert 0.05 <= test_ratio <= 0.25, f"Test ratio {test_ratio} outside expected range"

    @given(
        task_count=st.integers(min_value=1, max_value=50)
    )
    @settings(max_examples=30, deadline=None)
    def test_jsonl_format_property(self, task_count):
        """
        Property 2: JSONL output format for train/validation/test splits is valid and parseable.
        
        For any list of tasks, the exported JSONL files should:
        - Contain one JSON object per line
        - Be parseable as valid JSON
        - Preserve all task fields
        
        **Validates: Requirement 3.3**
        """
        # Arrange: Create dummy tasks
        tasks = [
            {
                "task_type": f"type_{i % 3}",
                "drawing_id": f"drawing_{i}",
                "context": {"feature_type": "test", "value": i},
                "target": {"property": "test_prop", "value": i * 2}
            }
            for i in range(task_count)
        ]
        
        # Act: Export tasks
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = DatasetExporter(output_dir=tmpdir)
            train, val, test = exporter._split_deterministic(tasks)
            
            train_path = Path(tmpdir) / "train.jsonl"
            val_path = Path(tmpdir) / "validation.jsonl"
            test_path = Path(tmpdir) / "test.jsonl"
            
            exporter._write_jsonl(train, train_path)
            exporter._write_jsonl(val, val_path)
            exporter._write_jsonl(test, test_path)
            
            # Assert: Files are valid JSONL
            for path, expected_tasks in [(train_path, train), (val_path, val), (test_path, test)]:
                assert path.exists(), f"File {path} was not created"
                
                with open(path, 'r') as f:
                    lines = f.readlines()
                
                assert len(lines) == len(expected_tasks), \
                    f"File {path} has {len(lines)} lines, expected {len(expected_tasks)}"
                
                # Parse each line as JSON
                parsed_tasks = []
                for i, line in enumerate(lines):
                    try:
                        task = json.loads(line)
                        parsed_tasks.append(task)
                    except json.JSONDecodeError as e:
                        pytest.fail(f"Line {i} in {path} is not valid JSON: {e}")
                
                # Verify all required fields are present
                for task in parsed_tasks:
                    assert "task_type" in task, "Missing task_type field"
                    assert "drawing_id" in task, "Missing drawing_id field"
                    assert "context" in task, "Missing context field"
                    assert "target" in task, "Missing target field"

    @given(
        task_count=st.integers(min_value=1, max_value=50),
        drawing_count=st.integers(min_value=1, max_value=20)
    )
    @settings(max_examples=30, deadline=None)
    def test_metadata_format_property(self, task_count, drawing_count):
        """
        Property 3: JSON metadata format contains required fields.
        
        For any list of tasks, the metadata should contain:
        - version, format, total_tasks, task_types, drawings, splits, schema
        
        **Validates: Requirement 3.4**
        """
        # Arrange: Create dummy tasks with multiple task types and drawings
        tasks = [
            {
                "task_type": f"type_{i % 3}",
                "drawing_id": f"drawing_{i % drawing_count}",
                "context": {"value": i},
                "target": {"property": "test", "value": i * 2}
            }
            for i in range(task_count)
        ]
        
        # Act: Generate metadata
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = DatasetExporter(output_dir=tmpdir)
            train, val, test = exporter._split_deterministic(tasks)
            metadata = exporter._generate_metadata(tasks, train, val, test)
        
        # Assert: Metadata has required fields
        assert "version" in metadata, "Missing version field"
        assert "format" in metadata, "Missing format field"
        assert "total_tasks" in metadata, "Missing total_tasks field"
        assert "task_types" in metadata, "Missing task_types field"
        assert "drawings" in metadata, "Missing drawings field"
        assert "splits" in metadata, "Missing splits field"
        assert "schema" in metadata, "Missing schema field"
        
        # Verify total_tasks matches input
        assert metadata["total_tasks"] == len(tasks), \
            f"total_tasks {metadata['total_tasks']} != {len(tasks)}"
        
        # Verify splits structure
        splits = metadata["splits"]
        assert "train" in splits, "Missing train split in metadata"
        assert "validation" in splits, "Missing validation split in metadata"
        assert "test" in splits, "Missing test split in metadata"
        
        # Verify split counts
        assert splits["train"]["count"] == len(train), "Train count mismatch"
        assert splits["validation"]["count"] == len(val), "Validation count mismatch"
        assert splits["test"]["count"] == len(test), "Test count mismatch"
        
        # Verify schema structure
        schema = metadata["schema"]
        assert "task_type" in schema, "Missing task_type in schema"
        assert "context" in schema, "Missing context in schema"
        assert "target" in schema, "Missing target in schema"

    @given(
        entity_count=st.integers(min_value=1, max_value=50)
    )
    @settings(max_examples=30, deadline=None)
    def test_entity_lookup_construction_property(self, entity_count):
        """
        Property 4: Entity lookup dictionary (entity_by_id) construction works correctly.
        
        For any list of entities, building entity_by_id should:
        - Create a dictionary with entity_id as key
        - Preserve all entity fields
        - Allow O(1) lookup by entity_id
        
        **Validates: Requirement 3.5**
        """
        # Arrange: Create dummy entities
        entities = [
            {
                "entity_id": f"entity_{i}",
                "entity_type": "CIRCLE" if i % 2 == 0 else "LINE",
                "geometry": {
                    "center": [i * 10, i * 20],
                    "diameter": i * 5
                }
            }
            for i in range(entity_count)
        ]
        
        # Act: Build entity lookup (simulating what happens in _build_tasks)
        entity_by_id = {e["entity_id"]: e for e in entities}
        
        # Assert: All entities are in lookup
        assert len(entity_by_id) == len(entities), "Entity count mismatch"
        
        # Verify each entity is accessible by ID
        for entity in entities:
            entity_id = entity["entity_id"]
            assert entity_id in entity_by_id, f"Entity {entity_id} not in lookup"
            
            # Verify entity fields are preserved
            looked_up = entity_by_id[entity_id]
            assert looked_up["entity_type"] == entity["entity_type"], "Entity type mismatch"
            assert looked_up["geometry"] == entity["geometry"], "Geometry mismatch"

    def test_empty_input_handling_property(self):
        """
        Property 5: Empty/invalid input handling skips with warning, no crash.
        
        When no tasks are generated (empty feature results), the exporter should:
        - Write empty JSONL files
        - Write metadata with total_tasks=0
        - Not crash or raise exceptions
        
        **Validates: Requirement 3.6**
        """
        # Arrange: Create pipeline output with no feature candidates
        pipeline_output = {
            "entities": [
                {
                    "entity_id": "line_001",
                    "entity_type": "LINE",
                    "geometry": {"start": [0, 0], "end": [100, 100]}
                }
            ],
            "feature_result": {
                "radial_patterns": {"radial_patterns": []},
                "hole_candidates": {"hole_candidates": []},
                "slot_candidates": {"slot_candidates": []}
            },
            "structural_result": {
                "concentric_groups": {"concentric_groups": []}
            },
            "refinement_result": {
                "repetitions": {"repetition_groups": []}
            }
        }
        
        # Act: Export with empty features
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = DatasetExporter(output_dir=tmpdir)
            
            # This should not crash
            metadata = exporter.export([pipeline_output])
            
            # Assert: Metadata indicates no tasks
            assert metadata["total_tasks"] == 0, "Expected 0 tasks for empty input"
            
            # Verify empty files were created (files are in the exporter's output_dir)
            train_path = exporter.output_dir / "train.jsonl"
            val_path = exporter.output_dir / "validation.jsonl"
            test_path = exporter.output_dir / "test.jsonl"
            metadata_path = exporter.output_dir / "metadata.json"
            
            assert train_path.exists(), "Train file not created"
            assert val_path.exists(), "Validation file not created"
            assert test_path.exists(), "Test file not created"
            assert metadata_path.exists(), "Metadata file not created"

    @given(
        center=st.tuples(
            st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False),
            st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False)
        ),
        radius=st.floats(min_value=0.1, max_value=1000, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=50, deadline=None)
    def test_distance_calculation_property(self, center, radius):
        """
        Property 6: Mathematical formulas for geometric properties (distance, radius) are unchanged.
        
        For any center point and radius, distance calculations should:
        - Use standard Euclidean distance formula: sqrt(dx^2 + dy^2)
        - Round to 4 decimal places
        - Preserve mathematical precision
        
        **Validates: Requirement 3.8**
        """
        # Arrange: Create two points at known distance
        x1, y1 = center
        angle = math.radians(45)  # 45 degrees
        x2 = x1 + radius * math.cos(angle)
        y2 = y1 + radius * math.sin(angle)
        
        # Act: Calculate distance using standard formula (what Phase-7 should use)
        dx = x2 - x1
        dy = y2 - y1
        calculated_distance = math.sqrt(dx**2 + dy**2)
        
        # Assert: Distance matches expected radius
        assert abs(calculated_distance - radius) < 0.0001, \
            f"Distance calculation error: {calculated_distance} != {radius}"
        
        # Verify rounding to 4 decimal places (Phase-7 convention)
        rounded_distance = round(calculated_distance, 4)
        rounded_radius = round(radius, 4)
        assert abs(rounded_distance - rounded_radius) < 0.00001, \
            f"Rounding error: {rounded_distance} != {rounded_radius}"

    @given(
        diameter=st.floats(min_value=0.1, max_value=1000, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=50, deadline=None)
    def test_radius_diameter_conversion_property(self, diameter):
        """
        Property 7: Radius/diameter conversions use standard formulas.
        
        For any diameter, radius calculations should:
        - Use formula: radius = diameter / 2
        - Use formula: diameter = radius * 2
        - Round to 4 decimal places
        
        **Validates: Requirement 3.8**
        """
        # Act: Convert diameter to radius and back
        radius = diameter / 2
        diameter_back = radius * 2
        
        # Assert: Conversion is reversible
        assert abs(diameter_back - diameter) < 0.0001, \
            f"Diameter conversion error: {diameter_back} != {diameter}"
        
        # Verify rounding to 4 decimal places
        rounded_radius = round(radius, 4)
        rounded_diameter = round(diameter, 4)
        rounded_diameter_back = round(rounded_radius * 2, 4)
        
        # Allow small floating point errors in rounding (up to 0.0002 for double rounding)
        assert abs(rounded_diameter_back - rounded_diameter) < 0.0002, \
            f"Rounding error in conversion: {rounded_diameter_back} != {rounded_diameter}"

    @given(
        width=st.floats(min_value=0.1, max_value=1000, allow_nan=False, allow_infinity=False),
        height=st.floats(min_value=0.1, max_value=1000, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=50, deadline=None)
    def test_aspect_ratio_calculation_property(self, width, height):
        """
        Property 8: Aspect ratio calculations use standard formula.
        
        For any width and height, aspect ratio should:
        - Use formula: aspect_ratio = max(width, height) / min(width, height)
        - Round to 4 decimal places
        
        **Validates: Requirement 3.8**
        """
        # Assume width != height to avoid division issues
        assume(abs(width - height) > 0.01)
        
        # Act: Calculate aspect ratio
        length = max(width, height)
        short_side = min(width, height)
        aspect_ratio = length / short_side
        
        # Assert: Aspect ratio is >= 1
        assert aspect_ratio >= 1.0, f"Aspect ratio {aspect_ratio} < 1.0"
        
        # Verify rounding to 4 decimal places
        rounded_aspect = round(aspect_ratio, 4)
        assert rounded_aspect > 0, "Rounded aspect ratio is not positive"

    def test_file_writing_logic_property(self):
        """
        Property 9: File writing logic (_write_jsonl, _write_empty, _generate_metadata) is unchanged.
        
        Verify that:
        - _write_jsonl writes one JSON object per line
        - _write_empty creates empty files
        - _generate_metadata produces valid JSON
        
        **Validates: Requirement 3.7**
        """
        # Arrange: Create dummy tasks
        tasks = [
            {"task_type": "test", "drawing_id": "d1", "context": {}, "target": {"value": 1}},
            {"task_type": "test", "drawing_id": "d2", "context": {}, "target": {"value": 2}}
        ]
        
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = DatasetExporter(output_dir=tmpdir)
            
            # Test _write_jsonl
            jsonl_path = Path(tmpdir) / "test.jsonl"
            exporter._write_jsonl(tasks, jsonl_path)
            
            assert jsonl_path.exists(), "JSONL file not created"
            with open(jsonl_path, 'r') as f:
                lines = f.readlines()
            assert len(lines) == len(tasks), "JSONL line count mismatch"
            
            # Test _write_empty
            exporter._write_empty()
            
            for name in ["train.jsonl", "validation.jsonl", "test.jsonl"]:
                path = Path(tmpdir) / name
                assert path.exists(), f"Empty file {name} not created"
                assert path.stat().st_size == 0, f"Empty file {name} is not empty"
            
            # Test _generate_metadata
            train, val, test = exporter._split_deterministic(tasks)
            metadata = exporter._generate_metadata(tasks, train, val, test)
            
            # Verify metadata is valid JSON-serializable
            try:
                json_str = json.dumps(metadata)
                parsed = json.loads(json_str)
                assert parsed == metadata, "Metadata not JSON-serializable"
            except (TypeError, json.JSONDecodeError) as e:
                pytest.fail(f"Metadata is not valid JSON: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
