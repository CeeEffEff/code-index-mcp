"""
Index Migration - Tools for migrating between index types.

This provides tools for migrating between different index types,
such as from JSON to Neo4j.
"""

import json
import logging
import os
from typing import Dict, Any, Optional

from .json_index_manager import get_index_manager as get_json_index_manager
from .neo4j_index_builder import Neo4jIndexBuilder
from .neo4j_index_manager import get_neo4j_index_manager
from .models import SymbolInfo, FileInfo

logger = logging.getLogger(__name__)


class IndexMigrationTool:
    """Tool for migrating between index types."""
    
    @staticmethod
    def migrate_json_to_neo4j(
        project_path: str,
        json_index_path: Optional[str] = None,
        neo4j_uri: str = "bolt://localhost:7687",
        neo4j_user: str = "neo4j",
        neo4j_password: str = "password",
        neo4j_database: str = "neo4j"
    ) -> bool:
        """
        Migrate from JSON index to Neo4j index.
        
        Args:
            project_path: Path to the project
            json_index_path: Path to the JSON index file (if None, will use default)
            neo4j_uri: Neo4j URI
            neo4j_user: Neo4j username
            neo4j_password: Neo4j password
            neo4j_database: Neo4j database name
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Migrating JSON index to Neo4j for project: {project_path}")
            
            # Get JSON index manager
            json_manager = get_json_index_manager()
            json_manager.set_project_path(project_path)
            
            # Load JSON index
            if json_index_path:
                # Load from specific path
                with open(json_index_path, 'r', encoding='utf-8') as f:
                    json_index = json.load(f)
            else:
                # Load using manager
                if not json_manager.load_index():
                    logger.error("Failed to load JSON index")
                    return False
                
                # Get the in-memory index from the builder
                json_index = json_manager.index_builder.get_index()
                
                if not json_index:
                    logger.error("JSON index is empty or not loaded")
                    return False
            
            logger.info(f"Loaded JSON index with {len(json_index.get('symbols', {}))} symbols")
            
            # Create Neo4j index builder
            neo4j_builder = Neo4jIndexBuilder(
                project_path,
                neo4j_uri,
                neo4j_user,
                neo4j_password,
                neo4j_database
            )
            
            # Clear existing Neo4j index
            neo4j_builder._clear_existing_index()
            
            # Create schema constraints
            neo4j_builder._create_schema_constraints()
            
            # Migrate files
            files_migrated = IndexMigrationTool._migrate_files(neo4j_builder, json_index)
            logger.info(f"Migrated {files_migrated} files to Neo4j")
            
            # Migrate symbols
            symbols_migrated = IndexMigrationTool._migrate_symbols(neo4j_builder, json_index)
            logger.info(f"Migrated {symbols_migrated} symbols to Neo4j")
            
            # Migrate metadata
            IndexMigrationTool._migrate_metadata(neo4j_builder, json_index)
            logger.info("Migrated metadata to Neo4j")
            
            # Close Neo4j connection
            neo4j_builder.close()
            
            logger.info("Migration completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error migrating JSON index to Neo4j: {e}")
            return False
    
    @staticmethod
    def _migrate_files(neo4j_builder: Neo4jIndexBuilder, json_index: Dict[str, Any]) -> int:
        """
        Migrate files from JSON index to Neo4j.
        
        Args:
            neo4j_builder: Neo4j index builder
            json_index: JSON index data
            
        Returns:
            Number of files migrated
        """
        files = json_index.get("files", {})
        count = 0
        
        for file_path, file_data in files.items():
            try:
                # Convert to FileInfo
                file_info = FileInfo(
                    file_path=file_path,
                    language=file_data.get("language", "unknown"),
                    line_count=file_data.get("line_count", 0),
                    symbols={},  # Will be populated from symbols
                    imports=file_data.get("imports", []),
                    exports=file_data.get("exports", [])
                )
                
                # Add to Neo4j
                neo4j_builder._add_file_to_neo4j(file_info)
                count += 1
                
            except Exception as e:
                logger.warning(f"Error migrating file {file_path}: {e}")
        
        return count
    
    @staticmethod
    def _migrate_symbols(neo4j_builder: Neo4jIndexBuilder, json_index: Dict[str, Any]) -> int:
        """
        Migrate symbols from JSON index to Neo4j.
        
        Args:
            neo4j_builder: Neo4j index builder
            json_index: JSON index data
            
        Returns:
            Number of symbols migrated
        """
        symbols = json_index.get("symbols", {})
        files = json_index.get("files", {})
        count = 0
        
        for symbol_id, symbol_data in symbols.items():
            try:
                # Get file path
                file_path = symbol_data.get("file", "")
                
                # Skip if file not found
                if not file_path or file_path not in files:
                    logger.warning(f"File not found for symbol {symbol_id}: {file_path}")
                    continue
                
                # Convert to SymbolInfo
                symbol_info = SymbolInfo(
                    type=symbol_data.get("type", "unknown"),
                    file=file_path,
                    line=symbol_data.get("line", 0),
                    signature=symbol_data.get("signature"),
                    docstring=symbol_data.get("docstring"),
                    called_by=symbol_data.get("called_by", [])
                )
                
                # Get file info
                file_info = FileInfo(
                    file_path=file_path,
                    language=files[file_path].get("language", "unknown"),
                    line_count=files[file_path].get("line_count", 0),
                    symbols={},
                    imports=files[file_path].get("imports", []),
                    exports=files[file_path].get("exports", [])
                )
                
                # Add to Neo4j
                neo4j_builder._add_symbol_to_neo4j(symbol_id, symbol_info, file_info)
                count += 1
                
            except Exception as e:
                logger.warning(f"Error migrating symbol {symbol_id}: {e}")
        
        return count
    
    @staticmethod
    def _migrate_metadata(neo4j_builder: Neo4jIndexBuilder, json_index: Dict[str, Any]) -> None:
        """
        Migrate metadata from JSON index to Neo4j.
        
        Args:
            neo4j_builder: Neo4j index builder
            json_index: JSON index data
        """
        metadata = json_index.get("metadata", {})
        
        # Convert to Neo4j format
        neo4j_metadata = {
            "project_path": metadata.get("project_path", ""),
            "indexed_files": metadata.get("indexed_files", 0),
            "index_version": "1.0.0-neo4j-migrated",
            "timestamp": metadata.get("timestamp", ""),
            "languages": metadata.get("languages", []),
            "total_symbols": len(json_index.get("symbols", {})),
            "migrated_from": "json"
        }
        
        # Store in Neo4j
        neo4j_builder._store_index_metadata(neo4j_metadata)
    
    @staticmethod
    def verify_migration(project_path: str) -> Dict[str, Any]:
        """
        Verify migration from JSON to Neo4j.
        
        Args:
            project_path: Path to the project
            
        Returns:
            Dictionary with verification results
        """
        try:
            # Get JSON index manager
            json_manager = get_json_index_manager()
            json_manager.set_project_path(project_path)
            
            # Load JSON index
            if not json_manager.load_index():
                return {"success": False, "error": "Failed to load JSON index"}
            
            # Get Neo4j index manager
            neo4j_manager = get_neo4j_index_manager()
            neo4j_manager.set_project_path(project_path)
            
            # Initialize Neo4j manager
            if not neo4j_manager.initialize():
                return {"success": False, "error": "Failed to initialize Neo4j index manager"}
            
            # Get JSON index status
            json_status = json_manager.get_index_status()
            
            # Get Neo4j index status
            neo4j_status = neo4j_manager.get_index_status()
            
            # Compare
            return {
                "success": True,
                "json": {
                    "file_count": json_status.get("file_count", 0),
                    "symbol_count": json_status.get("symbol_count", 0)
                },
                "neo4j": {
                    "file_count": neo4j_status.get("file_count", 0),
                    "symbol_count": neo4j_status.get("symbol_count", 0)
                },
                "match": {
                    "file_count": json_status.get("file_count", 0) == neo4j_status.get("file_count", 0),
                    "symbol_count": json_status.get("symbol_count", 0) == neo4j_status.get("symbol_count", 0)
                }
            }
            
        except Exception as e:
            logger.error(f"Error verifying migration: {e}")
            return {"success": False, "error": str(e)}


# Command-line interface for migration
def migrate_index_cli(args: Dict[str, Any]) -> int:
    """
    Command-line interface for index migration.
    
    Args:
        args: Command-line arguments
        
    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    try:
        # Set up logging
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        
        # Get arguments
        project_path = args.get("project_path")
        json_index_path = args.get("json_index_path")
        neo4j_uri = args.get("neo4j_uri", "bolt://localhost:7687")
        neo4j_user = args.get("neo4j_user", "neo4j")
        neo4j_password = args.get("neo4j_password", "password")
        neo4j_database = args.get("neo4j_database", "neo4j")
        verify = args.get("verify", False)
        
        # Validate project path
        if not project_path:
            logger.error("Project path is required")
            return 1
        
        if not os.path.isdir(project_path):
            logger.error(f"Project path does not exist: {project_path}")
            return 1
        
        # Migrate
        success = IndexMigrationTool.migrate_json_to_neo4j(
            project_path,
            json_index_path,
            neo4j_uri,
            neo4j_user,
            neo4j_password,
            neo4j_database
        )
        
        if not success:
            logger.error("Migration failed")
            return 1
        
        # Verify if requested
        if verify:
            verification = IndexMigrationTool.verify_migration(project_path)
            
            if not verification.get("success", False):
                logger.error(f"Verification failed: {verification.get('error', 'Unknown error')}")
                return 1
            
            logger.info("Verification results:")
            logger.info(f"JSON: {verification.get('json', {})}")
            logger.info(f"Neo4j: {verification.get('neo4j', {})}")
            logger.info(f"Match: {verification.get('match', {})}")
            
            if not all(verification.get("match", {}).values()):
                logger.warning("Verification found mismatches")
                return 2
        
        logger.info("Migration completed successfully")
        return 0
        
    except Exception as e:
        logger.error(f"Error in migration CLI: {e}")
        return 1
