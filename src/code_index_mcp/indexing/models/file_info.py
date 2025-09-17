"""
FileInfo model for representing file metadata.
"""

from dataclasses import dataclass
from functools import cached_property
from importlib.machinery import ModuleSpec, PathFinder
from typing import Dict, List, Optional, Any


@dataclass
class FileInfo:
    """Information about a source code file."""
    
    file_path: str  # path to the file
    language: str  # programming language
    line_count: int  # total lines in file
    symbols: Dict[str, List[str]]  # symbol categories (functions, classes, etc.)
    # import_specs: List[ModuleSpec | str]  # imported modules/packages
    imports: List[str]  # imported modules/packages
    exports: Optional[List[str]] = None  # exported symbols (for JS/TS modules)
    package: Optional[str] = None  # package name (for Java, Go, etc.)
    docstring: Optional[str] = None  # file-level documentation
    
    def __post_init__(self):
        """Initialize mutable defaults."""
        if self.exports is None:
            self.exports = []

    @cached_property
    def import_specs(self) -> dict[str, ModuleSpec]:
        return {spec.name:  spec for i in set(self.imports) if (spec := PathFinder.find_spec(i)) is not None}
    