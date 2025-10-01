"""
FileInfo model for representing file metadata.
"""

from dataclasses import dataclass
from functools import cached_property
import importlib
from importlib.machinery import ModuleSpec, PathFinder
from typing import Dict, List, Optional, Any
import logging

from .symbol_info import SymbolInfo
from .import_call_info import ImportCallInfo

logger = logging.getLogger(__name__)

@dataclass
class FileInfo:
    """Information about a source code file."""
    
    file_path: str  # path to the file
    language: str  # programming language
    line_count: int  # total lines in file
    symbols: Dict[str, List[str]]  # symbol categories (functions, classes, etc.)
    imports: List[str]  # imported modules/packages
    import_calls: Optional[Dict[str, ImportCallInfo]] = None  # imported modules/packages that are called
    import_symbols: Optional[Dict[str, SymbolInfo]] = None  # imported modules/packages that are called
    import_call_info_lookup: Optional[Dict[str, ImportCallInfo]] = None # calling functions to info
    exports: Optional[List[str]] = None  # exported symbols (for JS/TS modules)
    package: Optional[str] = None  # package name (for Java, Go, etc.)
    docstring: Optional[str] = None  # file-level documentation
    
    def __post_init__(self):
        """Initialize mutable defaults."""
        if self.exports is None:
            self.exports = []
        if self.import_calls is None:
            self.import_calls = {}
        if self.import_symbols is None:
            self.import_symbols = {}
        if self.import_call_info_lookup is None:
            self.import_call_info_lookup = {}
