"""
Python parsing strategy using AST - Optimized single-pass version.
"""

import ast
import os
import logging
from typing import Dict, List, Tuple, Set

from .base_strategy import ParsingStrategy
from ..models import SymbolInfo, FileInfo, ImportCallInfo, ModuleSpec

logger = logging.getLogger(__name__)


class PythonParsingStrategy(ParsingStrategy):
    """Python-specific parsing strategy using Python's built-in AST - Single Pass Optimized."""

    def get_language_name(self) -> str:
        return "python"

    def get_supported_extensions(self) -> List[str]:
        return [".py", ".pyw"]

    def parse_file(
        self, file_path: str, content: str, project_dir: str, venv_root: str = None, explore_imports=True
    ) -> Tuple[Dict[str, SymbolInfo], FileInfo]:
        """Parse Python file using AST with single-pass optimization."""
        symbols = {}
        functions = []
        classes = []
        imports = []
        import_calls = {}
        import_symbols = {}
        import_call_info_lookup = {}
        self.explore_imports = explore_imports
        try:
            tree = ast.parse(content)
            # Single-pass visitor that handles everything at once
            visitor = SinglePassVisitor(
                symbols,
                functions,
                classes,
                imports,
                import_calls,
                import_call_info_lookup,
                import_symbols,
                file_path,
                project_dir,
                venv_root=venv_root,
                explore_imports=explore_imports,
            )
            visitor.visit(tree)
        except SyntaxError as e:
            logger.exception(f"Syntax error in Python file {file_path}: {e}")
        except Exception as e:
            logger.exception(f"Error parsing Python file {file_path}: {e}")

        file_info = FileInfo(
            file_path=file_path,
            language=self.get_language_name(),
            line_count=len(content.splitlines()),
            symbols={"functions": functions, "classes": classes},
            imports=imports,
            import_calls=import_calls,
            import_symbols=import_symbols,
            import_call_info_lookup=import_call_info_lookup,
        )
        # try:
        #     visitor._analyze_import_calls(tree, symbols, file_info, project_dir)
        # except Exception as e:
        #     logger.warning(f"Error epanding import calls for Python file {file_path}: {e}", exc_info=True)
        return symbols, file_info


class SinglePassVisitor(ast.NodeVisitor):
    """Single-pass AST visitor that extracts symbols and analyzes calls in one traversal."""

    def __init__(
        self,
        symbols: Dict[str, SymbolInfo],
        functions: List[str],
        classes: List[str],
        imports: List[str],
        import_calls: Dict[str, ImportCallInfo],
        import_call_info_lookup: Dict[str, ImportCallInfo],
        import_symbols: Dict[str, SymbolInfo],
        file_path: str,
        project_dir: str,
        venv_root: str = None,
        explore_imports = False,
    ):
        self.symbols = symbols
        self.functions = functions
        self.import_calls = import_calls
        self.import_call_info_lookup = import_call_info_lookup
        self.import_symbols = import_symbols  # map imported symbol ids
        self.classes = classes
        self.imports = imports
        self._imports = []  # to keep track of imported symbols
        self._from_imports = {}  # to keep track of imported symbols using from
        self.file_path = file_path
        self.project_dir = project_dir
        self.venv_root = venv_root
        self.explore_imports = explore_imports

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
            type="class", file=self.file_path, line=node.lineno, docstring=docstring
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
            docstring=docstring,
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
            docstring=method_docstring,
        )

        # Store in symbols and lookup index
        self.symbols[method_symbol_id] = symbol_info
        self.symbol_lookup[method_name] = method_symbol_id
        self.symbol_lookup[node.name] = (
            method_symbol_id  # Also index by method name alone
        )
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
            self._imports.append(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        """Handle from...import statements."""
        if node.module:
            for alias in node.names:
                self.imports.append(f"{node.module}.{alias.name}")
                self._from_imports[f"{node.module}.{alias.name}"] = (
                    node.module,
                    alias.name,
                )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        """Visit function call and record relationship using O(1) lookup."""
        def _visit_call():
            called_function = None
            try:
                # Get the function name being called

                if isinstance(node.func, ast.Name):
                    # Direct function call: function_name()
                    called_function = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    # Method call: obj.method() or module.function()
                    called_function = node.func.attr
                if not called_function:
                    logger.info(f"{node=} {type(node)} {self.file_path} {node.lineno} called but not a function call so ?")
                    return

                if not self.current_function_stack:
                    logger.info(f"{called_function=} called but no function stack, trying as import call")
                    self.try_as_import_call(node, called_function, None)
                    return

                # TODO have I only considered once half of the call relationship for imports?
                
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

                            return

                # Try method name match for any class
                for name, symbol_id in self.symbol_lookup.items():
                    if not name.endswith(f".{called_function}"):
                        continue
                    symbol_info = self.symbols[symbol_id]
                    if symbol_info.type not in ["function", "method"]:
                        continue
                    if caller_function not in symbol_info.called_by:
                        symbol_info.called_by.append(caller_function)

                    return  #TODO check this
                
                # Try see if symbol being called is actually in different module
                self.try_as_import_call(node, called_function, caller_function)

            except Exception as e:
                # Silently handle parsing errors for complex call patterns
                logger.exception(e, exc_info=True)
        # finally:
        # Continue visiting child nodes
        _visit_call()
        self.generic_visit(node)

    def try_as_import_call(self, node, called_function, caller_function):
        if not self.explore_imports:
            return
        # If import ... then must be a module
        # If from ... import then can be module, var, class, func
        # If maybe chance of not module, then should try removing the last . split

        # Get existing info and symbol, add the caller if new
        if called_function in self.import_call_info_lookup and caller_function:
            import_call_info = self.import_call_info_lookup[called_function]
            import_symbol_id = import_call_info.called_symbol_id
            import_symbol_info = import_call_info.called_symbol_info
            if caller_function not in import_symbol_info.called_by:
                import_symbol_info.called_by.append(caller_function)
            
            return

        terms = (called_function,)
        if "." in called_function:
            terms = (called_function, called_function.split(".")[-1])
    
        
        matching_imports = [i for i in self.imports if i.endswith(terms)]
        
        # Was called in this file but no import matches - should have been a direct match
        if caller_function and not matching_imports:
            logger.debug(f"{called_function} was called by {caller_function} but no matching import found - Suggests called should be within the file.")
            return

        # If don't have caller, but do have import match, what does that mean?
        # Symbol was imported and called via another import, or false match
        if not caller_function:
            # Still create symbol so have a placeholder?
            pass
            
        import_specs = self.try_get_import_spec(matching_imports)
        logger.info(
            f"{self.imports=}\n"
            f"{called_function=}\n"
            f"{node.func=}\n"
            f"{matching_imports=}\n"
            f"{import_specs=}\n"
        )
        if not import_specs:
            return 

        import_spec = import_specs[matching_imports[0]]
        relative_path = os.path.relpath(
            import_spec.spec.origin, self.project_dir
        )
        import_symbol_id = self._create_symbol_id(
            relative_path, called_function
        )

        # Should we not be saving symbol as it hasn't been defined?
        # It does act as a placeholder, but the import_calls can also do that
        import_call_info = self.call_info_from_import(called_function, caller_function, import_spec, relative_path, import_symbol_id)


        logger.info(
            f"{relative_path=}\n"
            f"{import_symbol_id=}\n"
            f"{import_call_info=}"
        )

    def call_info_from_import(self, called_function, caller_function, import_spec: ModuleSpec, relative_path, import_symbol_id) -> ImportCallInfo:
        # Store in symbols and lookup index if it doesn't exist, else add the caller
        # Placeholder for another file
        if import_symbol_info := self.import_symbols.get(import_symbol_id , None):
            if caller_function and (caller_function not in import_symbol_info.called_by):
                import_symbol_info.called_by.append(caller_function)
                # self.import_symbol_lookup[caller_function] = import_symbol_id
        else:
            import_symbol_info = SymbolInfo(
                type=None,
                # type=import_spec.try_get_symbol_type(import_symbol_id) or "function",
                file=relative_path,
                line=-1,
                called_by=[caller_function] if caller_function else [],
            )
            self.import_symbols[import_symbol_id] = import_symbol_info
            # self.import_symbol_lookup[caller_function] = import_symbol_id

        if not (import_call_info := self.import_calls.get(import_symbol_id, None)):
            import_call_info = ImportCallInfo(
                import_spec=import_spec,
                import_relative_path=relative_path,
                called_symbol_id=import_symbol_id,
                called_symbol_info=import_symbol_info,
            )
            self.import_calls[import_symbol_id] = import_call_info
            self.import_call_info_lookup[caller_function] = import_call_info
        return import_call_info

    def try_get_import_spec(self, matching_imports: List[str]) -> Dict[str, ModuleSpec]:
        return {
            called_import: spec # USE i instead for lookup
            # spec.name: spec # USE i instead for lookup
            for called_import in matching_imports
            if (
                spec := (
                    ImportCallInfo.get_import_spec(
                        called_import, self.project_dir, self.project_dir, self._from_imports.get(called_import, (None, None))[0], venv_root=self.venv_root
                    )
                ) # TODO This need to use self._imports ? Bug?
            )
            is not None
        }

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

