"""
Test for Task 3.10: Verify context_result is properly passed through main.py pipeline.

This test verifies that:
1. context_result from Phase-6 is captured
2. context_result is passed to DatasetPipeline.run()
3. context_result is included in all_dataset_results structure
4. Context statistics are logged
"""
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
import pytest


def test_context_result_passed_to_dataset_pipeline():
    """
    Verify that context_result from Phase-6 is passed to DatasetPipeline.run().
    
    This test mocks the pipeline components and verifies that:
    - ContextPipeline.run() is called and returns context_result
    - DatasetPipeline.run() receives context_result parameter
    - context_result is included in the final all_dataset_results structure
    """
    # Mock context_result from Phase-6
    mock_context_result = {
        "relationships": {
            "relationships": [],
            "statistics": {
                "total_relationships": 5,
                "connected_candidates": 3,
            }
        },
        "clusters": {
            "clusters": [],
            "statistics": {
                "total_clusters": 2,
                "multi_candidate_clusters": 1,
            }
        },
        "statistics": {
            "relationships": {
                "total_relationships": 5,
                "connected_candidates": 3,
            },
            "clusters": {
                "total_clusters": 2,
            }
        }
    }
    
    # Mock dataset_result
    mock_dataset_result = {
        "final_dataset": {"statistics": {"total_samples": 10}},
        "statistics": {}
    }
    
    with patch('main.ExtractionPipeline') as MockExtraction, \
         patch('main.TopologyPipeline') as MockTopology, \
         patch('main.StructuralPipeline') as MockStructural, \
         patch('main.FeaturePipeline') as MockFeature, \
         patch('main.RefinementPipeline') as MockRefinement, \
         patch('main.ContextPipeline') as MockContext, \
         patch('main.DatasetPipeline') as MockDataset, \
         patch('main.DatasetExporter') as MockExporter, \
         patch('main.INPUT_DIR') as mock_input_dir, \
         patch('builtins.open', create=True) as mock_open, \
         patch('json.dump') as mock_json_dump:
        
        # Setup mock DXF file
        mock_dxf_file = Mock()
        mock_dxf_file.name = "test.dxf"
        mock_dxf_file.stem = "test"
        mock_input_dir.glob.return_value = [mock_dxf_file]
        
        # Setup mock pipeline results
        mock_extraction = MockExtraction.return_value
        mock_extraction.run.return_value = {
            "entities": [{"entity_type": "LINE", "id": "e1"}]
        }
        
        mock_topology = MockTopology.return_value
        mock_topology.run.return_value = {"edges": []}
        
        mock_structural = MockStructural.return_value
        mock_structural.run.return_value = {"concentric_groups": []}
        
        mock_feature = MockFeature.return_value
        mock_feature.run.return_value = {"hole_candidates": []}
        
        mock_refinement = MockRefinement.return_value
        mock_refinement.run.return_value = {"repetition_groups": []}
        
        # Setup ContextPipeline to return our mock context_result
        mock_context = MockContext.return_value
        mock_context.run.return_value = mock_context_result
        
        # Setup DatasetPipeline to return mock dataset_result
        mock_dataset = MockDataset.return_value
        mock_dataset.run.return_value = mock_dataset_result
        
        # Setup DatasetExporter
        mock_exporter = MockExporter.return_value
        mock_exporter.export.return_value = {
            "splits": {
                "train": {"count": 7},
                "validation": {"count": 2},
                "test": {"count": 1}
            }
        }
        
        # Import and run main
        import main
        main.main()
        
        # Verify ContextPipeline.run() was called
        assert mock_context.run.called, "ContextPipeline.run() should be called"
        
        # Verify DatasetPipeline.run() was called with context_result
        assert mock_dataset.run.called, "DatasetPipeline.run() should be called"
        
        # Get the call arguments
        call_args = mock_dataset.run.call_args
        
        # Verify context_result was passed as a keyword argument
        assert 'context_result' in call_args.kwargs, \
            "context_result should be passed to DatasetPipeline.run()"
        
        # Verify the context_result value matches what ContextPipeline returned
        assert call_args.kwargs['context_result'] == mock_context_result, \
            "context_result passed to DatasetPipeline should match ContextPipeline output"


def test_context_statistics_logged():
    """
    Verify that context statistics are logged after Phase-6.
    
    This test verifies that the logging includes:
    - total_relationships
    - total_clusters
    - connected_candidates
    """
    mock_context_result = {
        "statistics": {
            "relationships": {
                "total_relationships": 5,
                "connected_candidates": 3,
            },
            "clusters": {
                "total_clusters": 2,
            }
        }
    }
    
    with patch('main.ExtractionPipeline') as MockExtraction, \
         patch('main.TopologyPipeline') as MockTopology, \
         patch('main.StructuralPipeline') as MockStructural, \
         patch('main.FeaturePipeline') as MockFeature, \
         patch('main.RefinementPipeline') as MockRefinement, \
         patch('main.ContextPipeline') as MockContext, \
         patch('main.DatasetPipeline') as MockDataset, \
         patch('main.DatasetExporter') as MockExporter, \
         patch('main.INPUT_DIR') as mock_input_dir, \
         patch('main.logger') as mock_logger, \
         patch('builtins.open', create=True) as mock_open, \
         patch('json.dump') as mock_json_dump:
        
        # Setup mock DXF file
        mock_dxf_file = Mock()
        mock_dxf_file.name = "test.dxf"
        mock_dxf_file.stem = "test"
        mock_input_dir.glob.return_value = [mock_dxf_file]
        
        # Setup mock pipeline results
        mock_extraction = MockExtraction.return_value
        mock_extraction.run.return_value = {
            "entities": [{"entity_type": "LINE", "id": "e1"}]
        }
        
        mock_topology = MockTopology.return_value
        mock_topology.run.return_value = {"edges": []}
        
        mock_structural = MockStructural.return_value
        mock_structural.run.return_value = {"concentric_groups": []}
        
        mock_feature = MockFeature.return_value
        mock_feature.run.return_value = {"hole_candidates": []}
        
        mock_refinement = MockRefinement.return_value
        mock_refinement.run.return_value = {"repetition_groups": []}
        
        # Setup ContextPipeline to return our mock context_result
        mock_context = MockContext.return_value
        mock_context.run.return_value = mock_context_result
        
        # Setup DatasetPipeline
        mock_dataset = MockDataset.return_value
        mock_dataset.run.return_value = {
            "final_dataset": {"statistics": {"total_samples": 10}},
            "statistics": {}
        }
        
        # Setup DatasetExporter
        mock_exporter = MockExporter.return_value
        mock_exporter.export.return_value = {
            "splits": {
                "train": {"count": 7},
                "validation": {"count": 2},
                "test": {"count": 1}
            }
        }
        
        # Import and run main
        import main
        main.main()
        
        # Verify that logger.info was called with context statistics
        log_calls = [str(call) for call in mock_logger.info.call_args_list]
        
        # Check if any log call contains context statistics
        context_log_found = False
        for log_call in log_calls:
            if "relationships=5" in log_call and "clusters=2" in log_call and "connected_candidates=3" in log_call:
                context_log_found = True
                break
        
        assert context_log_found, \
            f"Context statistics should be logged. Log calls: {log_calls}"


def test_context_result_in_all_dataset_results():
    """
    Verify that context_result is included in all_dataset_results structure.
    
    This test verifies that the all_dataset_results list passed to DatasetExporter
    includes context_result for each drawing.
    """
    mock_context_result = {
        "relationships": {"relationships": []},
        "clusters": {"clusters": []},
        "statistics": {
            "relationships": {"total_relationships": 5},
            "clusters": {"total_clusters": 2}
        }
    }
    
    with patch('main.ExtractionPipeline') as MockExtraction, \
         patch('main.TopologyPipeline') as MockTopology, \
         patch('main.StructuralPipeline') as MockStructural, \
         patch('main.FeaturePipeline') as MockFeature, \
         patch('main.RefinementPipeline') as MockRefinement, \
         patch('main.ContextPipeline') as MockContext, \
         patch('main.DatasetPipeline') as MockDataset, \
         patch('main.DatasetExporter') as MockExporter, \
         patch('main.INPUT_DIR') as mock_input_dir, \
         patch('builtins.open', create=True) as mock_open, \
         patch('json.dump') as mock_json_dump:
        
        # Setup mock DXF file
        mock_dxf_file = Mock()
        mock_dxf_file.name = "test.dxf"
        mock_dxf_file.stem = "test"
        mock_input_dir.glob.return_value = [mock_dxf_file]
        
        # Setup mock pipeline results
        mock_extraction = MockExtraction.return_value
        mock_extraction.run.return_value = {
            "entities": [{"entity_type": "LINE", "id": "e1"}]
        }
        
        mock_topology = MockTopology.return_value
        mock_topology.run.return_value = {"edges": []}
        
        mock_structural = MockStructural.return_value
        mock_structural.run.return_value = {"concentric_groups": []}
        
        mock_feature = MockFeature.return_value
        mock_feature.run.return_value = {"hole_candidates": []}
        
        mock_refinement = MockRefinement.return_value
        mock_refinement.run.return_value = {"repetition_groups": []}
        
        # Setup ContextPipeline to return our mock context_result
        mock_context = MockContext.return_value
        mock_context.run.return_value = mock_context_result
        
        # Setup DatasetPipeline
        mock_dataset = MockDataset.return_value
        mock_dataset.run.return_value = {
            "final_dataset": {"statistics": {"total_samples": 10}},
            "statistics": {}
        }
        
        # Setup DatasetExporter
        mock_exporter = MockExporter.return_value
        mock_exporter.export.return_value = {
            "splits": {
                "train": {"count": 7},
                "validation": {"count": 2},
                "test": {"count": 1}
            }
        }
        
        # Import and run main
        import main
        main.main()
        
        # Verify DatasetExporter.export() was called
        assert mock_exporter.export.called, "DatasetExporter.export() should be called"
        
        # Get the all_dataset_results argument
        call_args = mock_exporter.export.call_args
        all_dataset_results = call_args[0][0]
        
        # Verify all_dataset_results is a list with at least one item
        assert isinstance(all_dataset_results, list), \
            "all_dataset_results should be a list"
        assert len(all_dataset_results) > 0, \
            "all_dataset_results should contain at least one drawing"
        
        # Verify each item has context_result
        for result in all_dataset_results:
            assert "context_result" in result, \
                "Each item in all_dataset_results should have context_result"
            assert result["context_result"] == mock_context_result, \
                "context_result should match ContextPipeline output"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
