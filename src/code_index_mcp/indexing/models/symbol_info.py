"""
SymbolInfo model for representing code symbols.
"""

from dataclasses import dataclass
from typing import Optional, List, Set


@dataclass
class SymbolInfo:
    """Information about a code symbol (function, class, method, etc.)."""

    type: str  # function, class, method, interface, etc.
    file: str  # file path where symbol is defined
    line: int  # line number where symbol starts
    signature: Optional[str] = None  # function/method signature
    docstring: Optional[str] = None  # documentation string
    called_by: Optional[List[str]] = None  # list of symbols that call this symbol
    stack_levels: Optional[Set[int]] = None
    decorator_list: Optional[List[str]] = None

    def __post_init__(self):
        """Initialize mutable defaults."""
        if self.called_by is None:
            self.called_by = []
        if self.stack_levels is None:
            self.stack_levels = set()
        if self.decorator_list is None:
            self.decorator_list = []
