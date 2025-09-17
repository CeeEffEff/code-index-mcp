"""
Code indexing utilities for the MCP server.

This module provides indexing systems optimized for LLM consumption:
1. Simple JSON-based indexing (default)
2. Neo4j graph database indexing for advanced relationship queries
"""

# Import utility functions that are still used
from .qualified_names import (
    generate_qualified_name,
    normalize_file_path
)

# Models
from .models import SymbolInfo, FileInfo

# JSON-based indexing system
from .json_index_builder import JSONIndexBuilder
from .json_index_manager import JSONIndexManager, get_index_manager as get_json_index_manager

# Neo4j-based indexing system
from .neo4j_index_builder import Neo4jIndexBuilder
from .neo4j_index_manager import Neo4jIndexManager, get_neo4j_index_manager

# Index provider interfaces
from .index_provider import IIndexProvider, IIndexManager, IndexMetadata

# Index factory for selecting index type
from .index_factory import IndexFactory, get_index_manager, JSON_INDEX_TYPE, NEO4J_INDEX_TYPE

# Index migration tools
from .index_migration import IndexMigrationTool

__all__ = [
    # Utility functions
    'generate_qualified_name',
    'normalize_file_path',
    
    # Models
    'SymbolInfo',
    'FileInfo',
    
    # Interfaces
    'IIndexProvider',
    'IIndexManager',
    'IndexMetadata',
    
    # JSON indexing
    'JSONIndexBuilder',
    'JSONIndexManager',
    'get_json_index_manager',
    
    # Neo4j indexing
    'Neo4jIndexBuilder',
    'Neo4jIndexManager',
    'get_neo4j_index_manager',
    
    # Factory
    'IndexFactory',
    'get_index_manager',
    'JSON_INDEX_TYPE',
    'NEO4J_INDEX_TYPE',
    
    # Migration
    'IndexMigrationTool'
]
