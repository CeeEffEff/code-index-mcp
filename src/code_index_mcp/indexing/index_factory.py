"""
Index Factory - Factory for creating index managers.

This provides a factory for creating the appropriate index manager
based on configuration, allowing seamless switching between
JSON and Neo4j index managers.
"""

import logging
import os
from typing import Optional, Dict, Any

from .json_index_manager import JSONIndexManager, get_index_manager as get_json_index_manager
from .neo4j_index_manager import Neo4jIndexManager, get_neo4j_index_manager
from .index_provider import IIndexManager

logger = logging.getLogger(__name__)

# Index manager types
JSON_INDEX_TYPE = "json"
NEO4J_INDEX_TYPE = "neo4j"

# Default index type
DEFAULT_INDEX_TYPE = JSON_INDEX_TYPE

# Environment variable for index type
INDEX_TYPE_ENV_VAR = "CODE_INDEX_TYPE"


class IndexFactory:
    """Factory for creating index managers."""
    
    @staticmethod
    def create_index_manager(index_type: Optional[str] = None) -> IIndexManager:
        """
        Create an index manager of the specified type.
        
        Args:
            index_type: Type of index manager to create (json or neo4j)
            
        Returns:
            An index manager instance
        """
        # If no index type specified, try to get from environment
        if not index_type:
            index_type = os.environ.get(INDEX_TYPE_ENV_VAR, DEFAULT_INDEX_TYPE)
        
        # Create the appropriate index manager
        if index_type.lower() == NEO4J_INDEX_TYPE:
            logger.info("Creating Neo4j index manager")
            return get_neo4j_index_manager()
        else:
            logger.info("Creating JSON index manager")
            return get_json_index_manager()
    
    @staticmethod
    def get_available_index_types() -> Dict[str, str]:
        """
        Get available index types.
        
        Returns:
            Dictionary of available index types and their descriptions
        """
        return {
            JSON_INDEX_TYPE: "JSON-based index (default)",
            NEO4J_INDEX_TYPE: "Neo4j graph database index"
        }
    
    @staticmethod
    def get_index_type_info(index_type: str) -> Dict[str, Any]:
        """
        Get information about an index type.
        
        Args:
            index_type: Type of index to get information about
            
        Returns:
            Dictionary with information about the index type
        """
        if index_type.lower() == NEO4J_INDEX_TYPE:
            return {
                "name": "Neo4j Index",
                "description": "Graph database index using Neo4j",
                "requires": ["neo4j"],
                "features": [
                    "Graph-based code representation",
                    "Advanced relationship queries",
                    "Powerful query language (Cypher)",
                    "Visualization capabilities"
                ],
                "configuration": {
                    "uri": "Neo4j URI (e.g., bolt://localhost:7687)",
                    "user": "Neo4j username",
                    "password": "Neo4j password",
                    "database": "Neo4j database name"
                }
            }
        else:
            return {
                "name": "JSON Index",
                "description": "Simple JSON-based index",
                "requires": [],
                "features": [
                    "Simple file-based storage",
                    "No external dependencies",
                    "Fast for small to medium projects",
                    "Human-readable index format"
                ],
                "configuration": {}
            }


# Convenience function to get an index manager
def get_index_manager(index_type: Optional[str] = None) -> IIndexManager | Neo4jIndexManager | JSONIndexManager:
    """
    Get an index manager of the specified type.
    
    Args:
        index_type: Type of index manager to get (json or neo4j)
        
    Returns:
        An index manager instance
    """
    return IndexFactory.create_index_manager(index_type)
