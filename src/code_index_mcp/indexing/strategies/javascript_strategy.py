"""
JavaScript parsing strategy using tree-sitter.
"""

import logging
from typing import Dict, List, Tuple, Optional
import tree_sitter
from tree_sitter_javascript import language
from .base_strategy import ParsingStrategy
from ..models import SymbolInfo, FileInfo

logger = logging.getLogger(__name__)


class JavaScriptParsingStrategy(ParsingStrategy):
    """JavaScript-specific parsing strategy using tree-sitter."""

    def __init__(self):
        self.js_language = tree_sitter.Language(language())

    def get_language_name(self) -> str:
        return "javascript"

    def get_supported_extensions(self) -> List[str]:
        return ['.js', '.jsx', '.mjs', '.cjs']

    def parse_file(self, file_path: str, content: str, project_dir: str, venv_root: str = None,) -> Tuple[Dict[str, SymbolInfo], FileInfo]:
        """Parse JavaScript file using tree-sitter."""
        symbols = {}
        functions = []
        classes = []
        imports = []
        exports = []

        parser = tree_sitter.Parser(self.js_language)
        tree = parser.parse(content.encode('utf8'))
        self._traverse_js_node(tree.root_node, content, file_path, symbols, functions, classes, imports, exports)

        file_info = FileInfo(
            file_path=file_path,
            language=self.get_language_name(),
            line_count=len(content.splitlines()),
            symbols={"functions": functions, "classes": classes},
            imports=imports,
            exports=exports
        )

        return symbols, file_info

    def _traverse_js_node(self, node, content: str, file_path: str, symbols: Dict[str, SymbolInfo],
                         functions: List[str], classes: List[str], imports: List[str], exports: List[str]):
        """Traverse JavaScript AST node."""
        if node.type == 'function_declaration':
            name = self._get_function_name(node, content)
            if name:
                symbol_id = self._create_symbol_id(file_path, name)
                signature = self._get_js_function_signature(node, content)
                symbols[symbol_id] = SymbolInfo(
                    type="function",
                    file=file_path,
                    line=node.start_point[0] + 1,
                    signature=signature
                )
                functions.append(name)

        # Handle arrow functions and function expressions in lexical declarations (const/let)
        elif node.type in ['lexical_declaration', 'variable_declaration']:
            # Look for const/let/var name = arrow_function or function_expression
            for child in node.children:
                if child.type == 'variable_declarator':
                    name_node = None
                    value_node = None
                    for declarator_child in child.children:
                        if declarator_child.type == 'identifier':
                            name_node = declarator_child
                        elif declarator_child.type in ['arrow_function', 'function_expression', 'function']:
                            value_node = declarator_child

                    if name_node and value_node:
                        name = content[name_node.start_byte:name_node.end_byte]
                        symbol_id = self._create_symbol_id(file_path, name)
                        # Create signature from the declaration
                        signature = content[child.start_byte:child.end_byte].split('\n')[0].strip()
                        symbols[symbol_id] = SymbolInfo(
                            type="function",
                            file=file_path,
                            line=child.start_point[0] + 1,  # Use child position, not parent
                            signature=signature
                        )
                        functions.append(name)

        elif node.type == 'class_declaration':
            name = self._get_class_name(node, content)
            if name:
                symbol_id = self._create_symbol_id(file_path, name)
                symbols[symbol_id] = SymbolInfo(
                    type="class",
                    file=file_path,
                    line=node.start_point[0] + 1
                )
                classes.append(name)

        elif node.type == 'method_definition':
            method_name = self._get_method_name(node, content)
            class_name = self._find_parent_class(node, content)
            if method_name and class_name:
                full_name = f"{class_name}.{method_name}"
                symbol_id = self._create_symbol_id(file_path, full_name)
                signature = self._get_js_function_signature(node, content)
                symbols[symbol_id] = SymbolInfo(
                    type="method",
                    file=file_path,
                    line=node.start_point[0] + 1,
                    signature=signature
                )
                # Add method to functions list for consistency
                functions.append(full_name)

        # Continue traversing children
        for child in node.children:
            self._traverse_js_node(child, content, file_path, symbols, functions, classes, imports, exports)

    def _get_function_name(self, node, content: str) -> Optional[str]:
        """Extract function name from tree-sitter node."""
        for child in node.children:
            if child.type == 'identifier':
                return content[child.start_byte:child.end_byte]
        return None

    def _get_class_name(self, node, content: str) -> Optional[str]:
        """Extract class name from tree-sitter node."""
        for child in node.children:
            if child.type == 'identifier':
                return content[child.start_byte:child.end_byte]
        return None

    def _get_method_name(self, node, content: str) -> Optional[str]:
        """Extract method name from tree-sitter node."""
        for child in node.children:
            if child.type == 'property_identifier':
                return content[child.start_byte:child.end_byte]
        return None

    def _find_parent_class(self, node, content: str) -> Optional[str]:
        """Find the parent class of a method."""
        parent = node.parent
        while parent:
            if parent.type == 'class_declaration':
                return self._get_class_name(parent, content)
            parent = parent.parent
        return None

    def _get_js_function_signature(self, node, content: str) -> str:
        """Extract JavaScript function signature."""
        return content[node.start_byte:node.end_byte].split('\n')[0].strip()
