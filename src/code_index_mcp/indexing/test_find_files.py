"""
Unit tests for find_files method in Neo4jIndexManager.

This module contains unit tests for the find_files method in Neo4jIndexManager,
focusing on testing the method with proper mocking.
"""

import unittest
from unittest.mock import Mock, patch
import logging
import re

from .neo4j_index_manager import Neo4jIndexManager, Neo4jIndexProvider

# Disable logging for tests
logging.disable(logging.CRITICAL)


class TestGlobToRegex(unittest.TestCase):
    """Test cases for _glob_to_regex helper method."""

    def setUp(self):
        """Set up test fixtures."""
        self.provider = Neo4jIndexProvider(Mock(), "/test/project")

    def test_simple_glob_patterns(self):
        """Test simple glob pattern conversion."""
        test_cases = [
            ("*", "^.*$"),
            ("*.py", "^.*\\.py$"),
            ("test_*.py", "^test_.*\\.py$"),
            ("src/*.js", "^src/.*\\.js$"),
            ("?", "^.$"),
            ("test?.py", "^test.\\.py$"),
            ("src/test_?.js", "^src/test_.\\.js$"),
        ]
        
        for glob_pattern, expected_regex in test_cases:
            result = self.provider._glob_to_regex(glob_pattern)
            self.assertEqual(expected_regex, result)
            # Verify the regex is valid
            try:
                re.compile(result)
            except re.error:
                self.fail(f"Invalid regex pattern: {result}")

    def test_complex_glob_patterns(self):
        """Test complex glob pattern conversion."""
        # Get the actual regex patterns from the implementation
        test_patterns = [
            "src/[abc]*.js",
            "test-[0-9].py",
            "*.{js,ts}",
            "src/**/*.py",
        ]
        
        for glob_pattern in test_patterns:
            result = self.provider._glob_to_regex(glob_pattern)
            # Just verify the regex is valid
            try:
                re.compile(result)
            except re.error:
                self.fail(f"Invalid regex pattern: {result}")

    def test_special_characters(self):
        """Test glob patterns with special regex characters."""
        # Get the actual regex patterns from the implementation
        test_patterns = [
            "file+name.py",
            "file(name).py",
            "file[name].py",
            "file.name.py",
        ]
        
        for glob_pattern in test_patterns:
            result = self.provider._glob_to_regex(glob_pattern)
            # Just verify the regex is valid
            try:
                re.compile(result)
            except re.error:
                self.fail(f"Invalid regex pattern: {result}")


class TestSearchFiles(unittest.TestCase):
    """Test cases for search_files method in Neo4jIndexProvider."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_driver = Mock()
        self.provider = Neo4jIndexProvider(self.mock_driver, "/test/project")

    def test_search_files_all(self):
        """Test search_files with '*' pattern."""
        # Create a list to store the expected file paths
        expected_files = ["file1.py", "file2.py", "src/file3.js"]
        
        # Create a mock session
        mock_session = Mock()
        
        # Create a list of mock records
        mock_records = []
        for file_path in expected_files:
            mock_record = {"path": file_path}
            mock_records.append(mock_record)
        
        # Configure the session's run method to return the mock records
        mock_session.run.return_value = mock_records
        
        # Configure the driver's session method to return the mock session as a context manager
        self.mock_driver.session.return_value = mock_session
        # Make the mock session act like a context manager
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=None)
        
        # Execute
        result = self.provider.search_files("*")
        
        # Verify
        self.assertEqual(expected_files, result)
        mock_session.run.assert_called_once()
        # Verify the query uses the regex pattern
        args, kwargs = mock_session.run.call_args
        self.assertIn("=~", args[0])  # Cypher regex operator
        self.assertEqual("^.*$", kwargs["pattern"])  # Regex pattern

    def test_search_files_pattern(self):
        """Test search_files with specific pattern."""
        # Create a list to store the expected file paths
        expected_files = ["file1.py", "file2.py"]
        
        # Create a mock session
        mock_session = Mock()
        
        # Create a list of mock records
        mock_records = []
        for file_path in expected_files:
            mock_record = {"path": file_path}
            mock_records.append(mock_record)
        
        # Configure the session's run method to return the mock records
        mock_session.run.return_value = mock_records
        
        # Configure the driver's session method to return the mock session as a context manager
        self.mock_driver.session.return_value = mock_session
        # Make the mock session act like a context manager
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=None)
        
        # Execute
        result = self.provider.search_files("*.py")
        
        # Verify
        self.assertEqual(expected_files, result)
        mock_session.run.assert_called_once()
        # Verify the query uses the regex pattern
        args, kwargs = mock_session.run.call_args
        self.assertIn("=~", args[0])  # Cypher regex operator
        self.assertEqual("^.*\\.py$", kwargs["pattern"])  # Regex pattern

    def test_search_files_error(self):
        """Test search_files error handling."""
        # Setup mock to raise exception
        self.mock_driver.session.side_effect = Exception("Test exception")
        
        # Execute
        result = self.provider.search_files("*.py")
        
        # Verify
        self.assertEqual([], result)  # Should return empty list on error


class TestFindFiles(unittest.TestCase):
    """Test cases for find_files method in Neo4jIndexManager."""

    def setUp(self):
        """Set up test fixtures."""
        self.manager = Neo4jIndexManager()
        self.manager.project_path = "/test/project"
        self.mock_provider = Mock()
        self.manager.index_provider = self.mock_provider

    def test_find_files_with_provider(self):
        """Test find_files when index_provider is initialized."""
        # Setup mock
        self.mock_provider.search_files.return_value = ["file1.py", "file2.py"]
        
        # Execute
        result = self.manager.find_files("*.py")
        
        # Verify
        self.assertEqual(["file1.py", "file2.py"], result)
        self.mock_provider.search_files.assert_called_once_with("*.py")

    def test_find_files_no_provider(self):
        """Test find_files when index_provider is not initialized."""
        # Setup
        self.manager.index_provider = None
        
        # Execute
        result = self.manager.find_files("*.py")
        
        # Verify
        self.assertEqual([], result)  # Should return empty list when provider not initialized

    def test_find_files_default_pattern(self):
        """Test find_files with default pattern."""
        # Setup mock
        self.mock_provider.search_files.return_value = ["file1.py", "file2.py", "src/file3.js"]
        
        # Execute
        result = self.manager.find_files()  # No pattern provided
        
        # Verify
        self.assertEqual(["file1.py", "file2.py", "src/file3.js"], result)
        self.mock_provider.search_files.assert_called_once_with("*")  # Default pattern

    def test_find_files_error_handling(self):
        """Test find_files error handling."""
        # Setup mock to raise exception
        self.mock_provider.search_files.side_effect = Exception("Test exception")
        
        # Execute
        result = self.manager.find_files("*.py")
        
        # Verify
        self.assertEqual([], result)  # Should return empty list on error


if __name__ == "__main__":
    unittest.main()
