"""Unit tests for SymbolIDNormalizer class."""

import os
import sys
import tempfile
from pathlib import Path
import pytest

from code_index_mcp.indexing.utils.symbol_id_normalizer import SymbolIDNormalizer


class TestSymbolIDNormalizer:
    """Test suite for SymbolIDNormalizer."""
    
    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "project"
            project_root.mkdir()
            
            # Create project structure
            src_dir = project_root / "src"
            src_dir.mkdir()
            (src_dir / "module.py").touch()
            (src_dir / "subdir").mkdir()
            (src_dir / "subdir" / "nested.py").touch()
            
            # Create venv structure
            venv_root = project_root / ".venv"
            venv_root.mkdir()
            site_packages = venv_root / "lib" / "python3.11" / "site-packages"
            site_packages.mkdir(parents=True)
            (site_packages / "requests").mkdir()
            (site_packages / "requests" / "api.py").touch()
            (site_packages / "django").mkdir()
            (site_packages / "django" / "http").mkdir()
            (site_packages / "django" / "http" / "response.py").touch()
            
            yield {
                'project_root': str(project_root),
                'venv_root': str(venv_root),
                'src_module': str(src_dir / "module.py"),
                'nested_module': str(src_dir / "subdir" / "nested.py"),
                'requests_api': str(site_packages / "requests" / "api.py"),
                'django_response': str(site_packages / "django" / "http" / "response.py"),
            }
    
    def test_init_with_project_root_only(self, temp_project):
        """Test initialization with only project root."""
        normalizer = SymbolIDNormalizer(temp_project['project_root'])
        
        assert normalizer.project_root == temp_project['project_root']
        assert normalizer.venv_root is None
        assert isinstance(normalizer.stdlib_paths, set)
        assert len(normalizer.stdlib_paths) > 0
    
    def test_init_with_venv_root(self, temp_project):
        """Test initialization with both project and venv roots."""
        normalizer = SymbolIDNormalizer(
            temp_project['project_root'],
            temp_project['venv_root']
        )
        
        assert normalizer.project_root == temp_project['project_root']
        assert normalizer.venv_root == temp_project['venv_root']
    
    def test_normalize_project_file(self, temp_project):
        """Test normalization of project files."""
        normalizer = SymbolIDNormalizer(
            temp_project['project_root'],
            temp_project['venv_root']
        )
        
        # Test simple project file
        normalized = normalizer.normalize_path(temp_project['src_module'])
        assert normalized == "src/module.py"
        assert not normalized.startswith("venv://")
        assert not normalized.startswith("stdlib://")
        assert not normalized.startswith("external://")
    
    def test_normalize_nested_project_file(self, temp_project):
        """Test normalization of nested project files."""
        normalizer = SymbolIDNormalizer(
            temp_project['project_root'],
            temp_project['venv_root']
        )
        
        normalized = normalizer.normalize_path(temp_project['nested_module'])
        assert normalized == "src/subdir/nested.py"
    
    def test_normalize_venv_file(self, temp_project):
        """Test normalization of venv package files."""
        normalizer = SymbolIDNormalizer(
            temp_project['project_root'],
            temp_project['venv_root']
        )
        
        # Test requests package
        normalized = normalizer.normalize_path(temp_project['requests_api'])
        assert normalized == "venv://requests/api.py"
    
    def test_normalize_nested_venv_file(self, temp_project):
        """Test normalization of nested venv package files."""
        normalizer = SymbolIDNormalizer(
            temp_project['project_root'],
            temp_project['venv_root']
        )
        
        # Test django package with nested structure
        normalized = normalizer.normalize_path(temp_project['django_response'])
        assert normalized == "venv://django/http/response.py"
    
    def test_normalize_stdlib_file(self, temp_project):
        """Test normalization of standard library files."""
        normalizer = SymbolIDNormalizer(temp_project['project_root'])
        
        # Find a real stdlib file (logging is almost always available)
        import logging
        logging_path = logging.__file__
        
        if logging_path:  # Some modules might not have __file__
            normalized = normalizer.normalize_path(logging_path)
            assert normalized.startswith("stdlib://")
            assert "logging" in normalized
            # Should not include site-packages
            assert "site-packages" not in normalized
    
    def test_normalize_external_file(self, temp_project):
        """Test normalization of external files (outside project and venv)."""
        normalizer = SymbolIDNormalizer(
            temp_project['project_root'],
            temp_project['venv_root']
        )
        
        # Create a file outside project and venv
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as tmp:
            external_path = tmp.name
        
        try:
            normalized = normalizer.normalize_path(external_path)
            assert normalized.startswith("external://")
            assert external_path.replace(os.sep, '/') in normalized
        finally:
            os.unlink(external_path)
    
    def test_create_symbol_id_project_file(self, temp_project):
        """Test symbol ID creation for project files."""
        normalizer = SymbolIDNormalizer(
            temp_project['project_root'],
            temp_project['venv_root']
        )
        
        symbol_id = normalizer.create_symbol_id(
            temp_project['src_module'],
            "my_function"
        )
        
        assert symbol_id == "src/module.py::my_function"
    
    def test_create_symbol_id_venv_file(self, temp_project):
        """Test symbol ID creation for venv files."""
        normalizer = SymbolIDNormalizer(
            temp_project['project_root'],
            temp_project['venv_root']
        )
        
        symbol_id = normalizer.create_symbol_id(
            temp_project['requests_api'],
            "get"
        )
        
        assert symbol_id == "venv://requests/api.py::get"
    
    def test_create_symbol_id_stdlib_file(self, temp_project):
        """Test symbol ID creation for stdlib files."""
        normalizer = SymbolIDNormalizer(temp_project['project_root'])
        
        import logging
        logging_path = logging.__file__
        
        if logging_path:
            symbol_id = normalizer.create_symbol_id(logging_path, "Logger")
            assert symbol_id.startswith("stdlib://")
            assert "::Logger" in symbol_id
            assert "logging" in symbol_id
    
    def test_consistency_across_instances(self, temp_project):
        """Test that different normalizer instances produce same results."""
        normalizer1 = SymbolIDNormalizer(
            temp_project['project_root'],
            temp_project['venv_root']
        )
        normalizer2 = SymbolIDNormalizer(
            temp_project['project_root'],
            temp_project['venv_root']
        )
        
        # Same file should produce same normalized path
        path1 = normalizer1.normalize_path(temp_project['requests_api'])
        path2 = normalizer2.normalize_path(temp_project['requests_api'])
        
        assert path1 == path2
        
        # Same symbol should produce same ID
        id1 = normalizer1.create_symbol_id(temp_project['requests_api'], "get")
        id2 = normalizer2.create_symbol_id(temp_project['requests_api'], "get")
        
        assert id1 == id2
    
    def test_relative_path_handling(self, temp_project):
        """Test that relative paths are handled correctly."""
        normalizer = SymbolIDNormalizer(
            temp_project['project_root'],
            temp_project['venv_root']
        )
        
        # Change to project directory and use relative path
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_project['project_root'])
            
            # Relative path should be normalized to same result as absolute
            rel_path = "src/module.py"
            abs_path = temp_project['src_module']
            
            normalized_rel = normalizer.normalize_path(rel_path)
            normalized_abs = normalizer.normalize_path(abs_path)
            
            assert normalized_rel == normalized_abs
        finally:
            os.chdir(original_cwd)
    
    def test_path_separator_normalization(self, temp_project):
        """Test that path separators are normalized to forward slashes."""
        normalizer = SymbolIDNormalizer(
            temp_project['project_root'],
            temp_project['venv_root']
        )
        
        normalized = normalizer.normalize_path(temp_project['nested_module'])
        
        # Should use forward slashes regardless of OS
        assert '\\' not in normalized
        assert '/' in normalized
    
    def test_is_in_project(self, temp_project):
        """Test _is_in_project helper method."""
        normalizer = SymbolIDNormalizer(
            temp_project['project_root'],
            temp_project['venv_root']
        )
        
        assert normalizer._is_in_project(temp_project['src_module'])
        assert normalizer._is_in_project(temp_project['nested_module'])
        assert not normalizer._is_in_project(temp_project['requests_api'])
    
    def test_is_in_venv(self, temp_project):
        """Test _is_in_venv helper method."""
        normalizer = SymbolIDNormalizer(
            temp_project['project_root'],
            temp_project['venv_root']
        )
        
        assert normalizer._is_in_venv(temp_project['requests_api'])
        assert normalizer._is_in_venv(temp_project['django_response'])
        assert not normalizer._is_in_venv(temp_project['src_module'])
    
    def test_is_in_stdlib(self, temp_project):
        """Test _is_in_stdlib helper method."""
        normalizer = SymbolIDNormalizer(temp_project['project_root'])
        
        import logging
        logging_path = logging.__file__
        
        if logging_path:
            assert normalizer._is_in_stdlib(logging_path)
        
        assert not normalizer._is_in_stdlib(temp_project['src_module'])
    
    def test_no_venv_root_handling(self, temp_project):
        """Test behavior when venv_root is not provided."""
        normalizer = SymbolIDNormalizer(temp_project['project_root'])
        
        # Without venv_root, venv files should be treated as external
        normalized = normalizer.normalize_path(temp_project['requests_api'])
        
        # Should not be categorized as venv since no venv_root was provided
        # Will likely be external or potentially stdlib (depending on path)
        assert not normalizer._is_in_venv(temp_project['requests_api'])
    
    def test_symbol_name_with_special_characters(self, temp_project):
        """Test symbol names with special characters."""
        normalizer = SymbolIDNormalizer(
            temp_project['project_root'],
            temp_project['venv_root']
        )
        
        # Test with various symbol names
        symbol_names = [
            "MyClass",
            "my_function",
            "MyClass.method",
            "__init__",
            "_private_method",
        ]
        
        for symbol_name in symbol_names:
            symbol_id = normalizer.create_symbol_id(
                temp_project['src_module'],
                symbol_name
            )
            assert symbol_id.endswith(f"::{symbol_name}")
            assert symbol_id.startswith("src/module.py::")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
