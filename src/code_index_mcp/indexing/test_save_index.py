"""
Unit tests for Neo4jIndexManager save_index method.

This module contains unit tests for the save_index method of the Neo4jIndexManager class,
focusing on testing the method with proper mocking.
"""

import unittest
from unittest.mock import Mock, patch
import logging
import os
import json
import tempfile

from .neo4j_index_manager import Neo4jIndexManager

# Disable logging for tests
logging.disable(logging.CRITICAL)


class TestNeo4jIndexManagerSaveIndex(unittest.TestCase):
    """Test cases for Neo4jIndexManager save_index method."""

    def setUp(self):
        """Set up test fixtures."""
        self.manager = Neo4jIndexManager()
        self.manager.project_path = "/test/project"
        self.manager.config_path = os.path.join(tempfile.gettempdir(), "test_neo4j_config.json")
        self.manager.neo4j_uri = "bolt://localhost:7687"
        self.manager.neo4j_user = "neo4j"
        self.manager.neo4j_password = "password"
        self.manager.neo4j_database = "neo4j"
        self.manager.clustering_enabled = True
        self.manager.clustering_k = 5
        self.manager.clustering_max_iterations = 50

    def tearDown(self):
        """Tear down test fixtures."""
        # Save config_path before cleanup
        config_path = self.manager.config_path
        self.manager.cleanup()
        # Remove test config file if it exists
        if config_path and os.path.exists(config_path):
            os.remove(config_path)

    def test_save_index_success(self):
        """Test save_index when _save_neo4j_config succeeds."""
        # Mock _save_neo4j_config to do nothing (success case)
        self.manager._save_neo4j_config = Mock()
        
        # Execute
        result = self.manager.save_index()
        
        # Verify
        self.assertTrue(result)
        self.manager._save_neo4j_config.assert_called_once()

    def test_save_index_exception(self):
        """Test save_index when _save_neo4j_config raises an exception."""
        # Mock _save_neo4j_config to raise an exception
        self.manager._save_neo4j_config = Mock(side_effect=Exception("Test exception"))
        
        # Execute
        result = self.manager.save_index()
        
        # Verify
        self.assertFalse(result)
        self.manager._save_neo4j_config.assert_called_once()

    def test_save_neo4j_config(self):
        """Test _save_neo4j_config method."""
        # Execute the actual _save_neo4j_config method
        self.manager._save_neo4j_config()
        
        # Verify
        self.assertTrue(os.path.exists(self.manager.config_path))
        
        # Check file content
        with open(self.manager.config_path, 'r') as f:
            config = json.load(f)
        
        # Verify config content
        self.assertEqual(self.manager.neo4j_uri, config["uri"])
        self.assertEqual(self.manager.neo4j_user, config["user"])
        self.assertEqual(self.manager.neo4j_password, config["password"])
        self.assertEqual(self.manager.neo4j_database, config["database"])
        self.assertEqual(self.manager.clustering_enabled, config["clustering"]["enabled"])
        self.assertEqual(self.manager.clustering_k, config["clustering"]["k"])
        self.assertEqual(self.manager.clustering_max_iterations, config["clustering"]["max_iterations"])

    def test_save_neo4j_config_no_config_path(self):
        """Test _save_neo4j_config when config_path is not set."""
        # Set config_path to None
        self.manager.config_path = None
        
        # Execute
        # This should not raise an exception, just log a warning
        self.manager._save_neo4j_config()
        
        # No assertion needed, just verifying it doesn't crash

    @patch('builtins.open')
    def test_save_neo4j_config_exception(self, mock_open):
        """Test _save_neo4j_config when an exception occurs."""
        # Mock open to raise an exception
        mock_open.side_effect = Exception("Test exception")
        
        # Execute
        # This should not raise an exception, just log an error
        self.manager._save_neo4j_config()
        
        # No assertion needed, just verifying it doesn't crash


if __name__ == "__main__":
    unittest.main()
