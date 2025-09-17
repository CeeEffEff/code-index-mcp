"""
Unit tests for Neo4jIndexManager class.

This module contains unit tests for the Neo4jIndexManager class,
focusing on testing individual methods with proper mocking.
"""

import unittest
from unittest.mock import Mock, patch
import logging
from typing import Dict, Any

from .neo4j_index_manager import Neo4jIndexManager

# Disable logging for tests
logging.disable(logging.CRITICAL)


class TestNeo4jIndexManager(unittest.TestCase):
    """Test cases for Neo4jIndexManager class."""

    def setUp(self):
        """Set up test fixtures."""
        self.manager = Neo4jIndexManager()
        self.manager.project_path = "/test/project"
        # Create a mock driver
        self.mock_driver = Mock()
        self.manager.driver = self.mock_driver

    def tearDown(self):
        """Tear down test fixtures."""
        self.manager.cleanup()

    def test_get_index_stats_driver_not_initialized(self):
        """Test get_index_stats when driver is not initialized."""
        # Setup
        self.manager.driver = None
        
        # Execute
        result = self.manager.get_index_stats()
        
        # Verify
        self.assertEqual({"status": "not_loaded"}, result)

    def test_get_index_stats_index_available(self):
        """Test get_index_stats when index is available."""
        # Setup
        # Mock get_index_status
        status_data = {
            "status": "available",
            "project_path": "/test/path",
            "file_count": 100,
            "symbol_count": 500,
            "class_count": 50,
            "function_count": 200,
            "languages": ["python", "javascript"],
            "index_version": "1.0",
            "timestamp": "2023-01-01T00:00:00"
        }
        self.manager.get_index_status = Mock(return_value=status_data)
        
        # Execute
        result = self.manager.get_index_stats()
        
        # Verify
        expected = {
            "status": "loaded",
            "project_path": "/test/path",
            "indexed_files": 100,
            "total_symbols": 500,
            "symbol_types": {
                "class": 50,
                "function": 200
            },
            "languages": ["python", "javascript"],
            "index_version": "1.0",
            "timestamp": "2023-01-01T00:00:00"
        }
        self.assertEqual(expected, result)

    def test_get_index_stats_index_not_available(self):
        """Test get_index_stats when index is not available."""
        # Setup
        # Mock get_index_status
        status_data = {
            "status": "empty",
            "project_path": "/test/path",
            "file_count": 0,
            "symbol_count": 0,
            "class_count": 0,
            "function_count": 0,
            "languages": [],
            "index_version": "unknown",
            "timestamp": "unknown"
        }
        self.manager.get_index_status = Mock(return_value=status_data)
        
        # Execute
        result = self.manager.get_index_stats()
        
        # Verify
        expected = {
            "status": "not_loaded",
            "project_path": "/test/path",
            "indexed_files": 0,
            "total_symbols": 0,
            "symbol_types": {
                "class": 0,
                "function": 0
            },
            "languages": [],
            "index_version": "unknown",
            "timestamp": "unknown"
        }
        self.assertEqual(expected, result)

    def test_get_index_stats_exception_handling(self):
        """Test get_index_stats exception handling."""
        # Setup
        self.manager.get_index_status = Mock(side_effect=Exception("Test exception"))
        
        # Execute
        result = self.manager.get_index_stats()
        
        # Verify
        self.assertEqual("error", result["status"])
        self.assertEqual("Test exception", result["error"])

    def test_get_index_stats_missing_fields(self):
        """Test get_index_stats with missing fields in status."""
        # Setup
        # Mock get_index_status with missing fields
        status_data = {
            "status": "available",
            # Missing project_path
            "file_count": 100,
            # Missing symbol_count
            # Missing class_count
            "function_count": 200,
            # Missing languages
            # Missing index_version
            # Missing timestamp
        }
        self.manager.get_index_status = Mock(return_value=status_data)
        
        # Execute
        result = self.manager.get_index_stats()
        
        # Verify
        expected = {
            "status": "loaded",
            "project_path": "/test/project",  # Should use manager's project_path
            "indexed_files": 100,
            "total_symbols": 0,  # Default value
            "symbol_types": {
                "class": 0,  # Default value
                "function": 200
            },
            "languages": [],  # Default value
            "index_version": "unknown",  # Default value
            "timestamp": "unknown"  # Default value
        }
        self.assertEqual(expected, result)
        
    def test_refresh_index_builder_not_initialized(self):
        """Test refresh_index when index builder is not initialized."""
        # Setup
        self.manager.index_builder = None
        
        # Execute
        result = self.manager.refresh_index()
        
        # Verify
        self.assertFalse(result)
        
    def test_refresh_index_success(self):
        """Test refresh_index when successful."""
        # Setup
        mock_builder = Mock()
        mock_builder.build_index.return_value = True
        self.manager.index_builder = mock_builder
        self.manager.clustering_enabled = True
        self.manager.clustering_k = 10
        
        # Execute
        result = self.manager.refresh_index()
        
        # Verify
        self.assertTrue(result)
        mock_builder.build_index.assert_called_once_with(
            run_clustering=True,
            k=10
        )
        
    def test_refresh_index_failure(self):
        """Test refresh_index when build_index fails."""
        # Setup
        mock_builder = Mock()
        mock_builder.build_index.return_value = False
        self.manager.index_builder = mock_builder
        
        # Execute
        result = self.manager.refresh_index()
        
        # Verify
        self.assertFalse(result)
        mock_builder.build_index.assert_called_once()
        
    def test_refresh_index_exception(self):
        """Test refresh_index when an exception occurs."""
        # Setup
        mock_builder = Mock()
        mock_builder.build_index.side_effect = Exception("Test exception")
        self.manager.index_builder = mock_builder
        
        # Execute
        result = self.manager.refresh_index()
        
        # Verify
        self.assertFalse(result)
        mock_builder.build_index.assert_called_once()
        
    def test_refresh_index_default_clustering_params(self):
        """Test refresh_index uses default clustering parameters when not set."""
        # Setup
        mock_builder = Mock()
        mock_builder.build_index.return_value = True
        self.manager.index_builder = mock_builder
        # Deliberately not setting clustering_enabled and clustering_k
        
        # Execute
        result = self.manager.refresh_index()
        
        # Verify
        self.assertTrue(result)
        mock_builder.build_index.assert_called_once_with(
            run_clustering=True,  # Default value
            k=5  # Default value
        )
    
    def test_set_project_path_success(self):
        """Test set_project_path when successful."""
        # Setup
        with patch('os.path.isdir', return_value=True), \
             patch('os.makedirs'), \
             patch.object(self.manager, 'initialize', return_value=True) as mock_initialize:
            
            # Execute
            result = self.manager.set_project_path("/test/valid/path")
            
            # Verify
            self.assertTrue(result)
            self.assertEqual("/test/valid/path", self.manager.project_path)
            mock_initialize.assert_called_once()
    
    def test_set_project_path_invalid_path(self):
        """Test set_project_path with invalid path."""
        # Setup
        with patch('os.path.isdir', return_value=False):
            
            # Execute
            result = self.manager.set_project_path("/test/invalid/path")
            
            # Verify
            self.assertFalse(result)
            # project_path should not be updated
            self.assertEqual("/test/project", self.manager.project_path)
    
    def test_set_project_path_initialize_fails(self):
        """Test set_project_path when initialize fails."""
        # Setup
        with patch('os.path.isdir', return_value=True), \
             patch('os.makedirs'), \
             patch.object(self.manager, 'initialize', return_value=False) as mock_initialize:
            
            # Execute
            result = self.manager.set_project_path("/test/valid/path")
            
            # Verify
            self.assertFalse(result)
            self.assertEqual("/test/valid/path", self.manager.project_path)
            mock_initialize.assert_called_once()
    
    def test_set_project_path_exception(self):
        """Test set_project_path when an exception occurs."""
        # Setup
        with patch('os.path.isdir', side_effect=Exception("Test exception")):
            
            # Execute
            result = self.manager.set_project_path("/test/path")
            
            # Verify
            self.assertFalse(result)
            # project_path should not be updated
            self.assertEqual("/test/project", self.manager.project_path)


if __name__ == "__main__":
    unittest.main()
