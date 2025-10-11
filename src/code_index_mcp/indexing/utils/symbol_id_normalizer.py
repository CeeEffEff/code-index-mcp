"""Symbol ID normalization utilities for consistent cross-file references.

This module provides path normalization to ensure that the same function/class
always generates the same symbol ID regardless of parsing context.
"""

import os
import sys
from pathlib import Path
from typing import Optional


class SymbolIDNormalizer:
    """Normalizes file paths and creates consistent symbol IDs.
    
    Ensures that symbols from different sources (project files, venv, stdlib, external)
    are always assigned the same ID regardless of when or how they are parsed.
    
    Path normalization strategy:
    - Project files: relative/path/to/file.py::SymbolName
    - Venv packages: venv://package/module.py::SymbolName
    - Standard library: stdlib://module.py::SymbolName
    - External: external:///abs/path/file.py::SymbolName
    """
    
    def __init__(self, project_root: str, venv_root: Optional[str] = None):
        """Initialize the normalizer with project and venv paths.
        
        Args:
            project_root: Absolute path to the project root directory
            venv_root: Optional absolute path to the virtual environment root
        """
        self.project_root = os.path.abspath(project_root)
        self.venv_root = os.path.abspath(venv_root) if venv_root else None
        
        # Determine standard library paths
        self.stdlib_paths = self._get_stdlib_paths()
    
    def _get_stdlib_paths(self) -> set[str]:
        """Get set of absolute paths to standard library directories.
        
        Returns:
            Set of absolute paths to stdlib locations
        """
        stdlib_paths = set()
        
        # Get paths from sys.path that are part of the Python installation
        for path_str in sys.path:
            path = Path(path_str).resolve()
            
            # Standard library is typically in lib/pythonX.Y/ directory
            if 'site-packages' not in str(path):
                # Check if this looks like a stdlib path
                if any(part.startswith('python') for part in path.parts):
                    stdlib_paths.add(str(path))
        
        # Also add the base prefix paths
        if hasattr(sys, 'base_prefix'):
            base_prefix = Path(sys.base_prefix).resolve()
            stdlib_paths.add(str(base_prefix / 'lib'))
        
        return stdlib_paths
    
    def _is_in_stdlib(self, file_path: str) -> bool:
        """Check if a file path is in the standard library.
        
        Args:
            file_path: Absolute or relative file path
            
        Returns:
            True if file is in standard library, False otherwise
        """
        abs_path = os.path.abspath(file_path)
        
        # Check if path starts with any known stdlib path
        for stdlib_path in self.stdlib_paths:
            if abs_path.startswith(stdlib_path):
                # Make sure it's not in site-packages
                if 'site-packages' not in abs_path:
                    return True
        
        return False
    
    def _is_in_venv(self, file_path: str) -> bool:
        """Check if a file path is in the virtual environment.
        
        Args:
            file_path: Absolute or relative file path
            
        Returns:
            True if file is in venv, False otherwise
        """
        if not self.venv_root:
            return False
        
        abs_path = os.path.abspath(file_path)
        return abs_path.startswith(self.venv_root)
    
    def _is_in_project(self, file_path: str) -> bool:
        """Check if a file path is in the project directory.
        
        Args:
            file_path: Absolute or relative file path
            
        Returns:
            True if file is in project, False otherwise
        """
        abs_path = os.path.abspath(file_path)
        return abs_path.startswith(self.project_root)
    
    def normalize_path(self, file_path: str) -> str:
        """Normalize a file path to a consistent format with appropriate prefix.
        
        Args:
            file_path: Absolute or relative file path
            
        Returns:
            Normalized path with prefix:
            - Relative path for project files
            - venv://package/module.py for venv packages
            - stdlib://module.py for standard library
            - external:///abs/path for external files
        """
        abs_path = os.path.abspath(file_path)
        
        # Check each category in priority order
        if self._is_in_project(abs_path):
            # Project file: use relative path from project root
            rel_path = os.path.relpath(abs_path, self.project_root)
            # Normalize path separators to forward slashes
            return rel_path.replace(os.sep, '/')
        
        elif self._is_in_venv(abs_path):
            # Venv file: extract package structure after site-packages
            if 'site-packages' in abs_path:
                # Find site-packages and get path after it
                parts = abs_path.split('site-packages' + os.sep, 1)
                if len(parts) == 2:
                    package_path = parts[1].replace(os.sep, '/')
                    return f"venv://{package_path}"
            
            # Fallback: use path relative to venv root
            rel_path = os.path.relpath(abs_path, self.venv_root)
            return f"venv://{rel_path.replace(os.sep, '/')}"
        
        elif self._is_in_stdlib(abs_path):
            # Standard library: extract module path
            # Try to get just the module structure (e.g., "email/mime/text.py")
            for stdlib_path in self.stdlib_paths:
                if abs_path.startswith(stdlib_path):
                    rel_path = os.path.relpath(abs_path, stdlib_path)
                    # Remove leading python version directories
                    parts = Path(rel_path).parts
                    # Skip pythonX.Y directory if present
                    start_idx = 0
                    for i, part in enumerate(parts):
                        if part.startswith('python'):
                            start_idx = i + 1
                            break
                    
                    clean_path = '/'.join(parts[start_idx:])
                    return f"stdlib://{clean_path}"
            
            # Fallback
            return f"stdlib://{Path(abs_path).name}"
        
        else:
            # External file: use absolute path with external prefix
            return f"external://{abs_path.replace(os.sep, '/')}"
    
    def create_symbol_id(self, file_path: str, symbol_name: str) -> str:
        """Create a consistent symbol ID from file path and symbol name.
        
        Args:
            file_path: Absolute or relative file path
            symbol_name: Name of the symbol (function, class, etc.)
            
        Returns:
            Symbol ID in format: normalized_path::symbol_name
        """
        normalized_path = self.normalize_path(file_path)
        return f"{normalized_path}::{symbol_name}"
