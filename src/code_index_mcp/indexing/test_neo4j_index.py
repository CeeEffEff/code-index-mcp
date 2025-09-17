"""
Test script for Neo4j index builder and manager.

This script demonstrates how to use the Neo4j index builder and manager
to create and query a Neo4j-based code index.
"""

import argparse
import logging
import os
import sys
from typing import Dict, Any
from .neo4j_index_manager import get_neo4j_index_manager
from .index_factory import get_index_manager, NEO4J_INDEX_TYPE
from .index_migration import IndexMigrationTool

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def test_neo4j_index(args: Dict[str, Any]) -> int:
    """
    Test Neo4j index builder and manager.
    
    Args:
        args: Command-line arguments
        
    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    try:
        # Get arguments
        project_path = args.get("project_path")
        neo4j_uri = args.get("neo4j_uri", "bolt://localhost:7687")
        neo4j_user = args.get("neo4j_user", "neo4j")
        neo4j_password = args.get("neo4j_password", "password")
        neo4j_database = args.get("neo4j_database", "neo4j")
        migrate = args.get("migrate", False)

        # Validate project path
        if not project_path:
            logger.error("Project path is required")
            return 1
        
        if not os.path.isdir(project_path):
            logger.error(f"Project path does not exist: {project_path}")
            return 1
        
        # Migrate from JSON if requested
        if migrate:
            logger.info("Migrating from JSON index...")
            success = IndexMigrationTool.migrate_json_to_neo4j(
                project_path,
                None,
                neo4j_uri,
                neo4j_user,
                neo4j_password,
                neo4j_database
            )
            
            if not success:
                logger.error("Migration failed")
                return 1
            
            logger.info("Migration completed successfully")
        
        # Get Neo4j index manager
        neo4j_manager = get_neo4j_index_manager()
        
        # Set Neo4j configuration
        neo4j_manager.set_neo4j_config(
            neo4j_uri,
            neo4j_user,
            neo4j_password,
            neo4j_database
        )
        
        # Set project path
        if not neo4j_manager.set_project_path(project_path):
            logger.error("Failed to set project path")
            return 1
        
        # Initialize Neo4j manager
        if not neo4j_manager.initialize():
            logger.error("Failed to initialize Neo4j index manager")
            return 1
        
        # Build index if not migrating
        if not migrate:
            logger.info("Building Neo4j index...")
            if not neo4j_manager.refresh_index(force=True):
                logger.error("Failed to build Neo4j index")
                return 1
            
            logger.info("Neo4j index built successfully")
        
        # Get index status
        status = neo4j_manager.get_index_status()
        logger.info(f"Neo4j index status: {status}")
        
        # Get index provider
        provider = neo4j_manager.get_provider()
        if not provider:
            logger.error("Failed to get Neo4j index provider")
            return 1
        
        # Get file list
        files = provider.get_file_list()
        logger.info(f"Found {len(files)} files in Neo4j index")
        
        # Show some files
        for i, file in enumerate(files[:5]):
            logger.info(f"File {i+1}: {file.file_path} ({file.language}, {file.line_count} lines)")
        
        # Get symbols for a file
        if files:
            file_path = files[0].file_path
            symbols = provider.query_symbols(file_path)
            logger.info(f"Found {len(symbols)} symbols in file {file_path}")
            
            # Show some symbols
            for i, symbol in enumerate(symbols[:5]):
                logger.info(f"Symbol {i+1}: {symbol.type} at line {symbol.line}")
        
        # Test using the factory
        logger.info("Testing index factory...")
        factory_manager = get_index_manager(NEO4J_INDEX_TYPE)
        factory_manager.set_project_path(project_path)
        factory_manager.initialize()
        
        factory_status = factory_manager.get_index_status()
        logger.info(f"Factory Neo4j index status: {factory_status}")
        
        logger.info("Neo4j index test completed successfully")
        return 0
        
    except Exception as e:
        logger.error(f"Error testing Neo4j index: {e}")
        return 1


def main():
    """Main entry point for the test script."""
    parser = argparse.ArgumentParser(description="Test Neo4j index builder and manager")
    parser.add_argument("--project-path", required=True, help="Path to the project")
    parser.add_argument("--neo4j-uri", default="bolt://localhost:7687", help="Neo4j URI")
    parser.add_argument("--neo4j-user", default="neo4j", help="Neo4j username")
    parser.add_argument("--neo4j-password", default="password", help="Neo4j password")
    parser.add_argument("--neo4j-database", default="neo4j", help="Neo4j database name")
    parser.add_argument("--migrate", action="store_true", help="Migrate from JSON index")
    
    args = parser.parse_args()
    
    # Convert args to dictionary
    args_dict = vars(args)
    
    # Run test
    return test_neo4j_index(args_dict)


if __name__ == "__main__":
    sys.exit(main())
