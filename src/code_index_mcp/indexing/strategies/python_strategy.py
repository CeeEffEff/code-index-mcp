"""
Python parsing strategy using AST - Optimized single-pass version.
"""

import ast
from collections import defaultdict
from importlib.machinery import PathFinder
import os
import logging
from typing import Dict, List, Tuple, Optional, Set
from .base_strategy import ParsingStrategy
from ..models import SymbolInfo, FileInfo

logger = logging.getLogger(__name__)


class PythonParsingStrategy(ParsingStrategy):
    """Python-specific parsing strategy using Python's built-in AST - Single Pass Optimized."""
    
    def get_language_name(self) -> str:
        return "python"
    
    def get_supported_extensions(self) -> List[str]:
        return ['.py', '.pyw']
    
    def parse_file(self, file_path: str, content: str, project_dir: str) -> Tuple[Dict[str, SymbolInfo], FileInfo]:
        """Parse Python file using AST with single-pass optimization."""
        symbols = {}
        functions = []
        classes = []
        imports = []
        
        try:
            tree = ast.parse(content)
            # Single-pass visitor that handles everything at once
            visitor = SinglePassVisitor(symbols, functions, classes, imports, file_path)
            visitor.visit(tree)
        except SyntaxError as e:
            logger.warning(f"Syntax error in Python file {file_path}: {e}")
        except Exception as e:
            logger.warning(f"Error parsing Python file {file_path}: {e}")
        
        file_info = FileInfo(
            file_path=file_path,
            language=self.get_language_name(),
            line_count=len(content.splitlines()),
            symbols={"functions": functions, "classes": classes},
            imports=imports
        )
        try:
            self._analyze_import_calls(tree, symbols, file_info, project_dir)
        except Exception as e:
            logger.warning(f"Error epanding import calls for Python file {file_path}: {e}", exc_info=True)
        return symbols, file_info


class SinglePassVisitor(ast.NodeVisitor):
    """Single-pass AST visitor that extracts symbols and analyzes calls in one traversal."""
    
    def __init__(self, symbols: Dict[str, SymbolInfo], functions: List[str], 
                 classes: List[str], imports: List[str], file_path: str):
        self.symbols = symbols
        self.functions = functions
        self.classes = classes
        self.imports = imports
        self.file_path = file_path
        
        # Context tracking for call analysis
        self.current_function_stack = []
        self.current_class = None
        
        # Symbol lookup index for O(1) access
        self.symbol_lookup = {}  # name -> symbol_id mapping for fast lookups
        
        # Track processed nodes to avoid duplicates
        self.processed_nodes: Set[int] = set()
    
    def visit_ClassDef(self, node: ast.ClassDef):
        """Visit class definition - extract symbol and analyze in single pass."""
        class_name = node.name
        symbol_id = self._create_symbol_id(self.file_path, class_name)
        
        # Extract docstring
        docstring = ast.get_docstring(node)
        
        # Create symbol info
        symbol_info = SymbolInfo(
            type="class",
            file=self.file_path,
            line=node.lineno,
            docstring=docstring
        )
        
        # Store in symbols and lookup index
        self.symbols[symbol_id] = symbol_info
        self.symbol_lookup[class_name] = symbol_id
        self.classes.append(class_name)
        
        # Track class context for method processing
        old_class = self.current_class
        self.current_class = class_name
        
        # Process class body (including methods)
        for child in node.body:
            if isinstance(child, ast.FunctionDef):
                self._handle_method(child, class_name)
            else:
                # Visit other nodes in class body
                self.visit(child)
        
        # Restore previous class context
        self.current_class = old_class
    
    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Visit function definition - extract symbol and track context."""
        # Skip if this is a method (already handled by ClassDef)
        if self.current_class:
            return
        
        # Skip if already processed
        node_id = id(node)
        if node_id in self.processed_nodes:
            return
        self.processed_nodes.add(node_id)
        
        func_name = node.name
        symbol_id = self._create_symbol_id(self.file_path, func_name)
        
        # Extract function signature and docstring
        signature = self._extract_function_signature(node)
        docstring = ast.get_docstring(node)
        
        # Create symbol info
        symbol_info = SymbolInfo(
            type="function",
            file=self.file_path,
            line=node.lineno,
            signature=signature,
            docstring=docstring
        )
        
        # Store in symbols and lookup index
        self.symbols[symbol_id] = symbol_info
        self.symbol_lookup[func_name] = symbol_id
        self.functions.append(func_name)
        
        # Track function context for call analysis
        function_id = f"{self.file_path}::{func_name}"
        self.current_function_stack.append(function_id)
        
        # Visit function body to analyze calls
        self.generic_visit(node)
        
        # Pop function from stack
        self.current_function_stack.pop()
    
    def _handle_method(self, node: ast.FunctionDef, class_name: str):
        """Handle method definition within a class."""
        method_name = f"{class_name}.{node.name}"
        method_symbol_id = self._create_symbol_id(self.file_path, method_name)
        
        method_signature = self._extract_function_signature(node)
        method_docstring = ast.get_docstring(node)
        
        # Create symbol info
        symbol_info = SymbolInfo(
            type="method",
            file=self.file_path,
            line=node.lineno,
            signature=method_signature,
            docstring=method_docstring
        )
        
        # Store in symbols and lookup index
        self.symbols[method_symbol_id] = symbol_info
        self.symbol_lookup[method_name] = method_symbol_id
        self.symbol_lookup[node.name] = method_symbol_id  # Also index by method name alone
        self.functions.append(method_name)
        
        # Track method context for call analysis
        function_id = f"{self.file_path}::{method_name}"
        self.current_function_stack.append(function_id)
        
        # Visit method body to analyze calls
        for child in node.body:
            self.visit(child)
        
        # Pop method from stack
        self.current_function_stack.pop()
    
    def visit_Import(self, node: ast.Import):
        """Handle import statements."""
        for alias in node.names:
            self.imports.append(alias.name)
        self.generic_visit(node)
    
    def visit_ImportFrom(self, node: ast.ImportFrom):
        """Handle from...import statements."""
        if node.module:
            for alias in node.names:
                self.imports.append(f"{node.module}.{alias.name}")
        self.generic_visit(node)
    
    def visit_Call(self, node: ast.Call):
        """Visit function call and record relationship using O(1) lookup."""
        if not self.current_function_stack:
            self.generic_visit(node)
            return
        
        try:
            # Get the function name being called
            called_function = None
            
            if isinstance(node.func, ast.Name):
                # Direct function call: function_name()
                called_function = node.func.id
            elif isinstance(node.func, ast.Attribute):
                # Method call: obj.method() or module.function()
                called_function = node.func.attr
            
            if called_function:
                # Get the current calling function
                caller_function = self.current_function_stack[-1]
                
                # Use O(1) lookup instead of O(n) iteration
                # First try exact match
                if called_function in self.symbol_lookup:
                    symbol_id = self.symbol_lookup[called_function]
                    symbol_info = self.symbols[symbol_id]
                    if symbol_info.type in ["function", "method"]:
                        if caller_function not in symbol_info.called_by:
                            symbol_info.called_by.append(caller_function)
                else:
                    # Try method name match for any class
                    for name, symbol_id in self.symbol_lookup.items():
                        if name.endswith(f".{called_function}"):
                            symbol_info = self.symbols[symbol_id]
                            if symbol_info.type in ["function", "method"]:
                                if caller_function not in symbol_info.called_by:
                                    symbol_info.called_by.append(caller_function)
                                break
        except Exception:
            # Silently handle parsing errors for complex call patterns
            pass
        
        # Continue visiting child nodes
        self.generic_visit(node)
    
    def _create_symbol_id(self, file_path: str, symbol_name: str) -> str:
        """Create a unique symbol ID."""
        return f"{file_path}::{symbol_name}"
    
    def _extract_function_signature(self, node: ast.FunctionDef) -> str:
        """Extract function signature from AST node."""
        # Build basic signature
        args = []
        
        # Regular arguments
        for arg in node.args.args:
            args.append(arg.arg)
        
        # Varargs (*args)
        if node.args.vararg:
            args.append(f"*{node.args.vararg.arg}")
        
        # Keyword arguments (**kwargs)
        if node.args.kwarg:
            args.append(f"**{node.args.kwarg.arg}")
        
        signature = f"def {node.name}({', '.join(args)}):"
        return signature

    def _analyze_calls(self, tree: ast.AST, symbols: Dict[str, SymbolInfo], file_path: str):
        """Analyze function calls and build caller-callee relationships."""
        visitor = CallAnalysisVisitor(symbols, file_path)
        visitor.visit(tree)

    def _analyze_import_calls(self, tree: ast.AST, symbols: Dict[str, SymbolInfo], file_info: FileInfo, project_dir: str):
        """Analyze function calls and build caller-callee relationships."""
        if file_info.import_specs:
            visitor = ImportCallAnalysisVisitor(file_info, project_dir, symbols)
            visitor.visit(tree)

class ImportCallAnalysisVisitor(ast.NodeVisitor):
    """AST visitor to analyze function calls and build caller-callee relationships."""
    
    def __init__(self, file_info: FileInfo, project_dir: str,  symbols: Dict[str, SymbolInfo]):
        self.symbols = symbols
        self.file_path = file_info.file_path
        self.current_function_stack = []
        self.current_class = None
        self.file_info = file_info
        self.project_dir = project_dir
    
    def visit_ClassDef(self, node: ast.ClassDef):
        """Visit class definition and track context."""
        # assert self.current_class is None
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = None
    
    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Visit function definition and track context."""
        # File path is already relative after our fix
        relative_path = self.file_path
        
        # Handle methods within classes
        if self.current_class:
            function_id = f"{relative_path}::{self.current_class}.{node.name}"
        else:
            function_id = f"{relative_path}::{node.name}"
            
        self.current_function_stack.append(function_id)
        
        # Visit all child nodes within this function
        self.generic_visit(node)
        
        # Pop the function from stack when done
        self.current_function_stack.pop()

    def visit_Call(self, node: ast.Call):
        """Visit function call and record relationship."""
        # new_symbols = defaultdict(lambda: list())
        new_symbols = {}
        try:
            # Get the function name being called
            called_function = None
            
            if isinstance(node.func, ast.Name):
                # Direct function call: function_name()
                called_function = node.func.id
            elif isinstance(node.func, ast.Attribute):
                # Method call: obj.method() or module.function()
                called_function = node.func.attr
                
            if called_function and (function_imports := [v for k, v in self.file_info.import_specs.items() if k.endswith(called_function) and v.origin]):
                # Look for the called function in our symbols and add relationship
                # The symbol is actually from another module
                # Duplicate it with an updated ID,=,
                # Look for the called function in our symbols and add relationship
                caller_function = self.current_function_stack[-1] if self.current_function_stack else "main"
                # for import_spec in function_imports:
                #     if not import_spec.origin:
                #         continue
                #     new_symbol = SymbolInfo(type="function" if "." not in called_function else "method",)
                for symbol_id, symbol_info in self.symbols.items():
                    if symbol_info.type in ["function", "method"]:
                        # Extract just the function/method name from the symbol ID
                        symbol_name = symbol_id.split("::")[-1]
                        
                        # Check for exact match or method name match (ClassName.method)
                        if (symbol_name == called_function or 
                            symbol_name.endswith(f".{called_function}")):
                            # Add caller to the called function's called_by list
                            # if caller_function not in symbol_info.called_by:
                                # symbol_info.called_by.append(caller_function)
                            for import_spec in function_imports:
                                old_symbol = symbol_info
                                
                                old_symbol["file"] = import_spec.origin
                                new_symbol_id = os.path.relpath(import_spec.origin, self.project_dir) + "::" + symbol_name
                                new_symbols[new_symbol_id] = SymbolInfo(type=symbol_info.type, file=import_spec.origin, line=-1, called_by=symbol_info.called_by, signature=symbol_info.signature, docstring=symbol_info.docstring)
                            break
                if not new_symbols:
                    for import_spec in function_imports:
                        new_symbol_id = os.path.relpath(import_spec.origin, self.project_dir) + "::" + called_function
                        new_symbols[new_symbol_id] = SymbolInfo(file=import_spec.origin, type="function" if "." not in called_function else "method", line=-1, called_by=[caller_function])
        except Exception:
            # Silently handle parsing errors for complex call patterns
            pass
        
        for symbol_id, symbol_info in new_symbols.items():
            if symbol_id not in self.symbols:
                # logger.info(f"Adding resolved import: {symbol_id=}")
                self.symbols[symbol_id] = symbol_info
            
        # Continue visiting child nodes
        self.generic_visit(node)

class CallAnalysisVisitor(ast.NodeVisitor):
    """AST visitor to analyze function calls and build caller-callee relationships."""
    
    def __init__(self, symbols: Dict[str, SymbolInfo], file_path: str):
        self.symbols = symbols
        self.file_path = file_path
        self.current_function_stack = []
        self.current_class = None
    
    def visit_ClassDef(self, node: ast.ClassDef):
        """Visit class definition and track context."""
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = None
    
    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Visit function definition and track context."""
        # File path is already relative after our fix
        relative_path = self.file_path
        
        # Handle methods within classes
        if self.current_class:
            function_id = f"{relative_path}::{self.current_class}.{node.name}"
        else:
            function_id = f"{relative_path}::{node.name}"
            
        self.current_function_stack.append(function_id)
        
        # Visit all child nodes within this function
        self.generic_visit(node)
        
        # Pop the function from stack when done
        self.current_function_stack.pop()
    
    def visit_Call(self, node: ast.Call):
        """Visit function call and record relationship."""
        try:
            # Get the function name being called
            called_function = None
            
            if isinstance(node.func, ast.Name):
                # Direct function call: function_name()
                called_function = node.func.id
            elif isinstance(node.func, ast.Attribute):
                # Method call: obj.method() or module.function()
                called_function = node.func.attr
                
            if called_function and self.current_function_stack:
                # Get the current calling function
                caller_function = self.current_function_stack[-1]
                
                # Look for the called function in our symbols and add relationship
                for symbol_id, symbol_info in self.symbols.items():
                    if symbol_info.type in ["function", "method"]:
                        # Extract just the function/method name from the symbol ID
                        symbol_name = symbol_id.split("::")[-1]
                        
                        # Check for exact match or method name match (ClassName.method)
                        if (symbol_name == called_function or 
                            symbol_name.endswith(f".{called_function}")):
                            # Add caller to the called function's called_by list
                            if caller_function not in symbol_info.called_by:
                                symbol_info.called_by.append(caller_function)
                            break
        except Exception:
            # Silently handle parsing errors for complex call patterns
            pass
            
        # Continue visiting child nodes
        self.generic_visit(node)
