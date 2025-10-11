"""
Neo4j Index Manager - Manages the lifecycle of the Neo4j-based index.

This implements the IIndexManager interface for Neo4j-based indexing,
providing a consistent interface for index management.
"""

import hashlib
import logging
import os
import tempfile
import threading
from typing import Dict, List, Optional, Any
import fnmatch
from neo4j import GraphDatabase, Driver

from .neo4j_index_builder import Neo4jIndexBuilder
from .index_provider import IIndexProvider, IIndexManager, IndexMetadata
from .models import SymbolInfo, FileInfo
from ..constants import SETTINGS_DIR, NEO4J_CONFIG_FILE

logger = logging.getLogger(__name__)


class Neo4jIndexProvider(IIndexProvider):
    """Neo4j-based index provider implementation."""
    
    def __init__(self, driver: Driver, project_path: str):
        self.driver = driver
        self.project_path = project_path
        logger.info("Initialized Neo4j Index Provider")
    
    def get_cluster_statistics(self) -> List[Dict[str, Any]]:
        """
        Get statistics for all clusters.
        
        Returns:
            List of cluster statistics dictionaries
        """
        try:
            with self.driver.session() as session:
                # First check if clusters exist
                check_result = session.run("MATCH (c:Cluster) RETURN count(c) as count")
                check_record = check_result.single()
                if not check_record or check_record["count"] == 0:
                    logger.exception("No clusters found in the database")
                    return []
                
                # Get cluster statistics
                result = session.run("""
                    MATCH (c:Cluster)
                    RETURN c.id as id, c.count as count, 
                           c.avg_outgoing_calls as avg_outgoing,
                           c.avg_incoming_calls as avg_incoming,
                           c.avg_args as avg_args,
                           c.avg_file_lines as avg_lines,
                           c.avg_file_imports as avg_imports
                    ORDER BY c.id
                """)
                
                clusters = [dict(record) for record in result]
                logger.info(f"Retrieved statistics for {len(clusters)} clusters")
                return clusters
                
        except Exception as e:
            logger.error(f"Error getting cluster statistics: {e}")
            return []

    def get_functions_in_cluster(self, cluster_id: int, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get functions in a specific cluster.
        
        Args:
            cluster_id: Cluster ID
            limit: Maximum number of functions to return (default: 100)
            
        Returns:
            List of function dictionaries
        """
        try:
            with self.driver.session() as session:
                # First check if the cluster exists
                check_result = session.run(
                    "MATCH (c:Cluster {id: $cluster_id}) RETURN count(c) as count", 
                    {"cluster_id": cluster_id}
                )
                check_record = check_result.single()
                if not check_record or check_record["count"] == 0:
                    logger.error(f"Cluster {cluster_id} not found in the database")
                    return []
                
                # Get functions in the cluster
                result = session.run("""
                    MATCH (f:Function)
                    WHERE f.cluster = $cluster_id
                    RETURN f.qualified_name as id, f.name as name, 
                           f.outgoing_calls as outgoing_calls,
                           f.incoming_calls as incoming_calls,
                           f.arg_count as arg_count,
                           f.file_line_count as file_line_count,
                           f.file_import_count as file_import_count
                    ORDER BY f.incoming_calls + f.outgoing_calls DESC
                    LIMIT $limit
                """, {"cluster_id": cluster_id, "limit": limit})
                
                functions = [dict(record) for record in result]
                logger.info(f"Retrieved {len(functions)} functions from cluster {cluster_id}")
                return functions
                
        except Exception as e:
            logger.error(f"Error getting functions in cluster {cluster_id}: {e}")
            return []
    
    def get_cross_file_calls(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Get cross-file function calls.
        
        Args:
            limit: Maximum number of cross-file calls to return (default: 100)
            
        Returns:
            List of cross-file call dictionaries
        """
        try:
            with self.driver.session() as session:
                # First check if there are any cross-file calls
                check_result = session.run("""
                    MATCH (caller_file:File)-[:CONTAINS]->(caller:Function)-[:CALLS]->(called:Function)<-[:CONTAINS]-(called_file:File)
                    WHERE caller_file.path <> called_file.path
                    RETURN count(*) as count
                """)
                check_record = check_result.single()
                if not check_record or check_record["count"] == 0:
                    logger.debug("No cross-file calls found in the database")
                    return []
                
                # Get cross-file calls
                result = session.run("""
                    MATCH (caller_file:File)-[:CONTAINS]->(caller:Function)-[:CALLS]->(called:Function)<-[:CONTAINS]-(called_file:File)
                    WHERE caller_file.path <> called_file.path
                    RETURN caller.name as caller_name, caller_file.path as caller_file,
                           called.name as called_name, called_file.path as called_file
                    LIMIT $limit
                """, {"limit": limit})
                
                calls = [dict(record) for record in result]
                logger.info(f"Retrieved {len(calls)} cross-file calls")
                return calls
                
        except Exception as e:
            logger.error(f"Error getting cross-file calls: {e}")
            return []
    
    def get_functions_with_most_cross_file_calls(self, limit: int = 20) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get functions with the most cross-file calls (either incoming or outgoing).
        
        Args:
            limit: Maximum number of functions to return (default: 20)
            
        Returns:
            Dictionary with 'outgoing' and 'incoming' lists of function dictionaries
        """
        try:
            with self.driver.session() as session:
                # First check if there are any cross-file calls
                check_result = session.run("""
                    MATCH (caller_file:File)-[:CONTAINS]->(caller:Function)-[:CALLS]->(called:Function)<-[:CONTAINS]-(called_file:File)
                    WHERE caller_file.path <> called_file.path
                    RETURN count(*) as count
                """)
                check_record = check_result.single()
                if not check_record or check_record["count"] == 0:
                    logger.debug("No cross-file calls found in the database")
                    return {"outgoing": [], "incoming": []}
                
                # Get functions with most outgoing cross-file calls
                result = session.run("""
                    MATCH (caller_file:File)-[:CONTAINS]->(caller:Function)-[:CALLS]->(called:Function)<-[:CONTAINS]-(called_file:File)
                    WHERE caller_file.path <> called_file.path
                    WITH caller, count(*) as outgoing_cross_file_calls
                    RETURN caller.qualified_name as id, caller.name as name, 
                           outgoing_cross_file_calls,
                           caller.incoming_calls as incoming_calls,
                           caller.outgoing_calls as outgoing_calls
                    ORDER BY outgoing_cross_file_calls DESC
                    LIMIT $limit
                """, {"limit": limit})
                
                outgoing = [dict(record) for record in result]
                logger.info(f"Retrieved {len(outgoing)} functions with most outgoing cross-file calls")
                
                # Get functions with most incoming cross-file calls
                result = session.run("""
                    MATCH (caller_file:File)-[:CONTAINS]->(caller:Function)-[:CALLS]->(called:Function)<-[:CONTAINS]-(called_file:File)
                    WHERE caller_file.path <> called_file.path
                    WITH called, count(*) as incoming_cross_file_calls
                    RETURN called.qualified_name as id, called.name as name, 
                           incoming_cross_file_calls,
                           called.incoming_calls as incoming_calls,
                           called.outgoing_calls as outgoing_calls
                    ORDER BY incoming_cross_file_calls DESC
                    LIMIT $limit
                """, {"limit": limit})
                
                incoming = [dict(record) for record in result]
                logger.info(f"Retrieved {len(incoming)} functions with most incoming cross-file calls")
                
                return {"outgoing": outgoing, "incoming": incoming}
                
        except Exception as e:
            logger.error(f"Error getting functions with most cross-file calls: {e}")
            return {"outgoing": [], "incoming": []}
    
    def get_file_list(self) -> List[FileInfo]:
        """
        Get list of all indexed files.
        
        Returns:
            List of file information objects
        """
        try:
            with self.driver.session() as session:
                result = session.run("""
                    MATCH (f:File)
                    RETURN f.path as path, f.language as language, 
                           f.line_count as line_count, f.imports as imports, 
                           f.exports as exports
                """)
                
                files = []
                for record in result:
                    files.append(FileInfo(
                        file_path=record["path"],
                        language=record["language"],
                        line_count=record["line_count"],
                        symbols={},  # We'll populate this from symbols if needed
                        imports=record["imports"] or [],
                        exports=record["exports"] or []
                    ))
                
                return files
                
        except Exception as e:
            logger.error(f"Error getting file list: {e}")
            return []
    
    def get_file_info(self, file_path: str) -> Optional[FileInfo]:
        """
        Get information for a specific file.
        
        Args:
            file_path: Relative file path
            
        Returns:
            File information, or None if file is not in index
        """
        try:
            # Normalize file path
            file_path = file_path.replace('\\', '/')
            if file_path.startswith('./'):
                file_path = file_path[2:]
                
            with self.driver.session() as session:
                result = session.run("""
                    MATCH (f:File {path: $path})
                    RETURN f.path as path, f.language as language, 
                           f.line_count as line_count, f.imports as imports, 
                           f.exports as exports
                """, {"path": file_path})
                
                record = result.single()
                if not record:
                    return None
                
                # Get symbols for this file
                symbols_result = session.run("""
                    MATCH (f:File {path: $path})-[:CONTAINS]->(s:Symbol)
                    RETURN s.type as type, s.name as name
                """, {"path": file_path})
                
                # Group symbols by type
                symbols_by_type = {}
                for symbol_record in symbols_result:
                    symbol_type = symbol_record["type"]
                    symbol_name = symbol_record["name"]
                    if symbol_type not in symbols_by_type:
                        symbols_by_type[symbol_type] = []
                    symbols_by_type[symbol_type].append(symbol_name)
                    
                return FileInfo(
                    file_path=record["path"],
                    language=record["language"],
                    line_count=record["line_count"],
                    symbols=symbols_by_type,
                    imports=record["imports"] or [],
                    exports=record["exports"] or []
                )
                
        except Exception as e:
            logger.error(f"Error getting file info for {file_path}: {e}")
            return None
    
    def query_symbols(self, file_path: str) -> List[SymbolInfo]:
        """
        Query symbol information in a file.
        
        Args:
            file_path: Relative file path
            
        Returns:
            List of symbol information objects
        """
        try:
            # Normalize file path
            file_path = file_path.replace('\\', '/')
            if file_path.startswith('./'):
                file_path = file_path[2:]
                
            with self.driver.session() as session:
                result = session.run("""
                    MATCH (f:File {path: $path})-[:CONTAINS]->(s:Symbol)
                    OPTIONAL MATCH (caller:Symbol)-[:CALLS]->(s)
                    RETURN s.qualified_name as id, s.name as name, s.type as type, 
                           s.line as line, s.signature as signature, s.docstring as docstring,
                           collect(distinct caller.qualified_name) as called_by
                """, {"path": file_path})
                
                symbols = []
                for record in result:
                    symbols.append(SymbolInfo(
                        type=record["type"],
                        file=file_path,
                        line=record["line"],
                        signature=record["signature"],
                        docstring=record["docstring"],
                        called_by=record["called_by"]
                    ))
                
                return symbols
                
        except Exception as e:
            logger.error(f"Error querying symbols for {file_path}: {e}")
            return []
    
    def _glob_to_regex(self, pattern: str) -> str:
        """
        Convert glob pattern to regex pattern for Neo4j queries.
        
        Args:
            pattern: Glob pattern string (e.g., "*.py", "src/*.js")
            
        Returns:
            Regex pattern string suitable for Neo4j Cypher queries
        """
        # Special case for common patterns
        if pattern == "*":
            return "^.*$"

        # Get the regex pattern from fnmatch.translate
        regex_pattern = fnmatch.translate(pattern)
        
        # Extract the pattern from the (?s:...) wrapper that fnmatch adds
        if regex_pattern.startswith('(?s:'):
            # Remove the (?s: prefix and the ) suffix
            regex_pattern = regex_pattern[4:-1]
            
            # Ensure we don't have any trailing )\ from the wrapper
            if regex_pattern.endswith(')\\'): 
                regex_pattern = regex_pattern[:-2]
        
        # Replace \Z with $ at the end
        regex_pattern = regex_pattern.replace('\\Z', '$')
        
        # Add ^ at the beginning if not already there
        if not regex_pattern.startswith('^'):
            regex_pattern = "^" + regex_pattern
            
        # Ensure the pattern ends with $ for proper matching
        if not regex_pattern.endswith('$'):
            regex_pattern = regex_pattern + '$'
            
        return regex_pattern
    
    def search_files(self, pattern: str) -> List[str]:
        """
        Search files by pattern.
        
        Args:
            pattern: Glob pattern or regular expression
            
        Returns:
            List of matching file paths
        """
        try:
            # Input validation
            if not isinstance(pattern, str):
                logger.error(f"Pattern must be a string, got {type(pattern)}")
                return []
                
            pattern = pattern.strip()
            if not pattern:
                pattern = "*"
            
            # Convert glob pattern to regex
            regex_pattern = self._glob_to_regex(pattern)
            logger.debug(f"Converted glob pattern '{pattern}' to regex '{regex_pattern}'")
            
            with self.driver.session() as session:
                query = """
                MATCH (f:File)
                WHERE f.path =~ $pattern
                RETURN f.path as path
                """
                
                result = session.run(query, pattern=regex_pattern)
                files = [record["path"] for record in result]
                
                logger.debug(f"Found {len(files)} files matching pattern '{pattern}'")
                return files
                
        except Exception as e:
            logger.error(f"Error searching files with pattern '{pattern}': {e}")
            return []
    
    def get_metadata(self) -> IndexMetadata:
        """
        Get index metadata.
        
        Returns:
            Index metadata information
        """
        try:
            with self.driver.session() as session:
                result = session.run("MATCH (m:IndexMetadata) RETURN m")
                
                record = result.single()
                if not record:
                    # Default metadata if none exists
                    return IndexMetadata(
                        version="unknown",
                        format_type="neo4j",
                        created_at=0,
                        last_updated=0,
                        file_count=0,
                        project_root=self.project_path,
                        tool_version="unknown"
                    )
                
                metadata = record["m"]
                
                # Count files
                file_count_result = session.run("MATCH (f:File) RETURN count(f) as count")
                file_count_record = file_count_result.single()
                file_count = file_count_record["count"] if file_count_record else 0
                
                return IndexMetadata(
                    version=metadata.get("index_version", "unknown"),
                    format_type="neo4j",
                    created_at=0,  # Convert timestamp to float
                    last_updated=0,  # Convert timestamp to float
                    file_count=file_count,
                    project_root=metadata.get("project_path", self.project_path),
                    tool_version="1.0.0"
                )
                
        except Exception as e:
            logger.error(f"Error getting metadata: {e}")
            return IndexMetadata(
                version="unknown",
                format_type="neo4j",
                created_at=0,
                last_updated=0,
                file_count=0,
                project_root=self.project_path,
                tool_version="unknown"
            )
    
    def is_available(self) -> bool:
        """
        Check if index is available.
        
        Returns:
            True if index is available and functional
        """
        try:
            with self.driver.session() as session:
                result = session.run("MATCH (m:IndexMetadata) RETURN count(m) as count")
                record = result.single()
                return record and record["count"] > 0
                
        except Exception as e:
            logger.error(f"Error checking index availability: {e}")
            return False


class Neo4jIndexManager(IIndexManager):
    """Manages Neo4j-based code index lifecycle and storage."""
    
    def __init__(self):
        self.project_path: Optional[str] = None
        self.neo4j_uri: Optional[str] = None
        self.neo4j_user: Optional[str] = None
        self.neo4j_password: Optional[str] = None
        self.neo4j_database: str = "neo4j"
        self.driver: Optional[Driver] = None
        self.index_builder: Optional[Neo4jIndexBuilder] = None
        self.index_provider: Optional[Neo4jIndexProvider] = None
        self.config_path: Optional[str] = None
        self._lock = threading.RLock()
        self.temp_dir = None
        self.venv_path: Optional[str] = None
        logger.info("Initialized Neo4j Index Manager")
    
    def find_files(self, pattern: str = "*") -> List[str]:
        """
        Find files matching a pattern.
        
        Args:
            pattern: Glob pattern (e.g., "*.py", "src/*.js")
            
        Returns:
            List of matching file paths
        """
        with self._lock:
            if not self.index_provider:
                logger.warning(f"Cannot find files matching '{pattern}': Index provider not initialized")
                return []
            
            try:
                logger.debug(f"Searching for files matching pattern: {pattern}")
                return self.index_provider.search_files(pattern)
            except Exception as e:
                logger.error(f"Error in find_files('{pattern}'): {e}")
                return []


    def get_file_summary(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Get summary information for a file.
        
        This method attempts to retrieve comprehensive file information including
        symbol counts, functions, classes, methods, and imports. If the index
        is not loaded, it will attempt auto-initialization to restore from the
        most recent index state.
        
        Args:
            file_path: Relative path to the file
            
        Returns:
            Dictionary containing file summary information, or None if not found
        """
        with self._lock:
            if not self.index_provider:
                logger.warning(f"Cannot find files matching '{file_path}': Index provider not initialized")
                return None
            
            # Input validation
            if not isinstance(file_path, str):
                logger.error(f"File path must be a string, got {type(file_path)}")
                return None
                
            file_path = file_path.strip()
            if not file_path:
                logger.error("File path cannot be empty")
                return None
            

            
            try:
                # Normalize file path
                file_path = file_path.replace('\\', '/')
                if file_path.startswith('./'):
                    file_path = file_path[2:]
                
                return self.index_provider.get_file_info(file_path)
                
            except Exception as e:
                logger.error(f"Error getting file summary: {e}")
                return None

    def initialize(self) -> bool:
        """Initialize the index manager."""
        with self._lock:
            if not self.project_path:
                logger.error("Project path not set")
                return False
                
            try:
                # self._cleanup()
                
                # Store current configuration (explicitly set values)
                current_config = {
                    "uri": self.neo4j_uri,
                    "user": self.neo4j_user,
                    "password": self.neo4j_password,
                    "database": self.neo4j_database,
                    "config_path": self.config_path
                }
                
                # Load Neo4j configuration from file or environment
                
                self._load_neo4j_config()
                
                # Restore explicitly set values (non-None values)
                if current_config["uri"] is not None:
                    self.neo4j_uri = current_config["uri"]
                if current_config["user"] is not None:
                    self.neo4j_user = current_config["user"]
                if current_config["password"] is not None:
                    self.neo4j_password = current_config["password"]
                if current_config["database"] is not None:
                    self.neo4j_database = current_config["database"]
                
                # Ensure we have defaults for any values that are still None
                if self.neo4j_uri is None:
                    self.neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
                if self.neo4j_user is None:
                    self.neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
                if self.neo4j_password is None:
                    self.neo4j_password = os.environ.get("NEO4J_PASSWORD", "password")
                if self.neo4j_database is None:
                    self.neo4j_database = os.environ.get("NEO4J_DATABASE", "neo4j")
                
                # Connect to Neo4j
                self.driver = GraphDatabase.driver(
                    self.neo4j_uri, 
                    auth=(self.neo4j_user, self.neo4j_password),
                    database=self.neo4j_database
                )
                
                # Test connection
                with self.driver.session() as session:
                    session.run("RETURN 1")
                
                # Create index builder and provider
                self.index_builder = Neo4jIndexBuilder(
                    self.project_path,
                    self.neo4j_uri,
                    self.neo4j_user,
                    self.neo4j_password,
                    self.neo4j_database,
                    venv_path=self.venv_path
                )
                
                self.index_provider = Neo4jIndexProvider(self.driver, self.project_path)
                self._save_neo4j_config()

                logger.info(f"Initialized Neo4j Index Manager for {self.project_path}")
                return True
                
            except Exception as e:
                logger.error(f"Failed to initialize Neo4j Index Manager: {e}")
                return False

    def get_provider(self) -> Optional[IIndexProvider]:
        """Get the current active index provider."""
        return self.index_provider
    
    def set_clustering_config(self, enabled=True, k=5, max_iterations=50):
        """
        Set configuration for K-means clustering.
        
        Args:
            enabled: Whether clustering is enabled (default: True)
            k: Number of clusters (default: 5)
            max_iterations: Maximum number of iterations (default: 50)
            
        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            try:
                self.clustering_enabled = enabled
                self.clustering_k = k
                self.clustering_max_iterations = max_iterations
                
                # Save configuration
                self._save_neo4j_config()
                
                logger.info(f"Set clustering configuration: enabled={enabled}, k={k}, max_iterations={max_iterations}")
                return True
                
            except Exception as e:
                logger.error(f"Failed to set clustering configuration: {e}")
                return False


    def build_index(self, ctx=None, force_rebuild: bool = False) -> bool:
        """Build or rebuild the index."""
        return self.refresh_index(ctx=ctx)

    def refresh_index(self, ctx=None) -> bool:
        """Refresh the index (rebuild and reload)."""
        with self._lock:
            if not self.index_builder:
                logger.error("Index builder not initialized")
                return False
            
            try:
                logger.info("Refreshing Neo4j index...")
                if self.index_builder.build_index(
                    run_clustering=getattr(self, 'clustering_enabled', True),
                    k=getattr(self, 'clustering_k', 5),
                    max_iterations=getattr(self, 'clustering_max_iterations', 50),
                    ctx=ctx
                ):
                    self.save_index()
                    return True
                return False
            except Exception as e:
                logger.error(f"Failed to refresh index: {e}")
                return False
    
    def save_index(self) -> bool:
        """Save index state."""
        # Neo4j index is automatically saved in the database, but we should
        # save any configuration or state that might be needed
        with self._lock:
            try:
                self._save_neo4j_config()
                logger.info("Saved Neo4j index configuration")
                return True
            except Exception as e:
                logger.error(f"Failed to save Neo4j configuration: {e}")
                return False
    
    def clear_index(self) -> None:
        """Clear index state."""
        with self._lock:
            if not self.driver:
                logger.error("Neo4j driver not initialized")
                return
            
            try:
                with self.driver.session() as session:
                    session.run("MATCH (n) DETACH DELETE n")
                logger.info("Cleared Neo4j index")
                
            except Exception as e:
                logger.error(f"Failed to clear index: {e}")
    
    def load_index(self) -> bool:
        """Load existing index from disk."""
        with self._lock:
            # self.refresh_index()
            status = self.get_index_status()
            return status.get("status") == "available"
    
    def get_index_status(self) -> Dict[str, Any]:
        """Get index status information."""
        with self._lock:
            if not self.driver:
                return {"status": "not_initialized"}
            
            try:
                with self.driver.session() as session:
                    # Get node counts
                    result = session.run("""
                        MATCH (f:File) WITH count(f) as file_count
                        MATCH (s:Symbol) WITH file_count, count(s) as symbol_count
                        MATCH (s:Symbol:Class) WITH file_count, symbol_count, count(s) as class_count
                        MATCH (s:Symbol:Function) WITH file_count, symbol_count, class_count, count(s) as function_count
                        OPTIONAL MATCH (c:Cluster) WITH file_count, symbol_count, class_count, function_count, count(c) as cluster_count
                        RETURN file_count, symbol_count, class_count, function_count, cluster_count
                    """)
                    
                    record = result.single()
                    if not record:
                        return {"status": "empty"}
                    
                    # Get metadata
                    metadata_result = session.run("MATCH (m:IndexMetadata) RETURN m")
                    metadata_record = metadata_result.single()
                    metadata = metadata_record["m"] if metadata_record else {}
                    
                    status_info = {
                        "status": "available",
                        "file_count": record["file_count"],
                        "symbol_count": record["symbol_count"],
                        "class_count": record["class_count"],
                        "function_count": record["function_count"],
                        "cluster_count": record["cluster_count"],
                        "project_path": metadata.get("project_path", self.project_path),
                        "venv_path": metadata.get("venv_path", self.venv_path),
                        "index_version": metadata.get("index_version", "unknown"),
                        "languages": metadata.get("languages", []),
                        "timestamp": metadata.get("timestamp", "unknown")
                    }
                    
                    # Add clustering information if available
                    if metadata.get("clustering_k"):
                        status_info["clustering"] = {
                            "k": metadata.get("clustering_k"),
                            "timestamp": metadata.get("clustering_timestamp")
                        }
                    
                    return status_info
                    
            except Exception as e:
                logger.error(f"Error getting index status: {e}")
                return {"status": "error", "error": str(e)}
    
    def get_index_stats(self) -> Dict[str, Any]:
        """Get statistics about the current index."""
        with self._lock:
            if not self.driver:
                return {"status": "not_loaded"}
            
            try:
                status = self.get_index_status()
                
                return {
                    "status": "loaded" if status.get("status") == "available" else "not_loaded",
                    "project_path": status.get("project_path", self.project_path),
                    "indexed_files": status.get("file_count", 0),
                    "total_symbols": status.get("symbol_count", 0),
                    "symbol_types": {
                        "class": status.get("class_count", 0),
                        "function": status.get("function_count", 0)
                    },
                    "languages": status.get("languages", []),
                    "index_version": status.get("index_version", "unknown"),
                    "timestamp": status.get("timestamp", "unknown")
                }
                    
            except Exception as e:
                logger.error(f"Error getting index stats: {e}")
                return {"status": "error", "error": str(e)}

    def set_project_path(self, project_path: str, init = True) -> bool:
        """Set the project path and initialize index storage."""
        with self._lock:
            try:
                # Input validation
                if not project_path or not isinstance(project_path, str):
                    logger.error(f"Invalid project path: {project_path}")
                    return False
                
                project_path = project_path.strip()
                if not project_path:
                    logger.error("Project path cannot be empty")
                    return False
                
                if not os.path.isdir(project_path):
                    logger.error(f"Project path does not exist: {project_path}")
                    return False
                
                self.project_path = project_path
                logger.info(f"Set project path: {project_path}")
                
                # Auto-initialize after setting project path to match JSON implementation behavior
                return self.initialize() if init else True
            except Exception as e:
                logger.error(f"Failed to set project path and initialize: {e}")
                return False

    def set_venv_path(self, venv_path: str, init = True) -> bool:
        """Set the project path and initialize index storage."""
        with self._lock:
            try:
                # Input validation
                if not venv_path or not isinstance(venv_path, str):
                    logger.error(f"Invalid venv_path: {venv_path}")
                    return False
                
                venv_path = venv_path.strip()
                if not venv_path:
                    logger.error("venv_path cannot be empty")
                    return False
                
                if not os.path.isdir(venv_path):
                    logger.error(f"venv_path does not exist: {venv_path}")
                    return False
                
                self.venv_path = venv_path
                logger.info(f"Set venv_path: {venv_path}")

                # Auto-initialize after setting project path to match JSON implementation behavior
                return self.initialize() if init else True
                
            except Exception as e:
                logger.error(f"Failed to set venv path and initialize: {e}")
                return False
    
    def _load_neo4j_config(self):
        """Load Neo4j configuration from file or environment."""
        import json
        
        # Default values
        self.neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        self.neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
        self.neo4j_password = os.environ.get("NEO4J_PASSWORD", "password")
        self.neo4j_database = os.environ.get("NEO4J_DATABASE", "neo4j")
        self.config_path = os.environ.get("NEO4J_IDX_CFG_PATH", self.config_path)
        
        # Default clustering configuration
        self.clustering_enabled = True
        self.clustering_k = 5
        self.clustering_max_iterations = 50
        
        # Try to load from config file
        if self.config_path and os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                
                self.neo4j_uri = config.get("uri", self.neo4j_uri)
                self.neo4j_user = config.get("user", self.neo4j_user)
                self.neo4j_password = config.get("password", self.neo4j_password)
                self.neo4j_database = config.get("database", self.neo4j_database)
                
                # Load clustering configuration if available
                if "clustering" in config:
                    clustering_config = config["clustering"]
                    self.clustering_enabled = clustering_config.get("enabled", True)
                    self.clustering_k = clustering_config.get("k", 5)
                    self.clustering_max_iterations = clustering_config.get("max_iterations", 50)
                
                logger.info(f"Loaded Neo4j configuration from {self.config_path}")
                
            except Exception as e:
                logger.warning(f"Failed to load Neo4j configuration from {self.config_path}: {e}")
    
    def _save_neo4j_config(self):
        """Save Neo4j configuration to file."""
        import json
        
        if not self.config_path:
            logger.warning("Config path not set, cannot save Neo4j configuration")
            return
        
        try:
            config = {
                "uri": self.neo4j_uri,
                "user": self.neo4j_user,
                "password": self.neo4j_password,
                "database": self.neo4j_database,
                "clustering": {
                    "enabled": getattr(self, 'clustering_enabled', True),
                    "k": getattr(self, 'clustering_k', 5),
                    "max_iterations": getattr(self, 'clustering_max_iterations', 50)
                }
            }
            
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=2)
                
            logger.info(f"Saved Neo4j configuration to {self.config_path}")
            
        except Exception as e:
            logger.error(f"Failed to save Neo4j configuration: {e}")
    
    # def set_neo4j_config(self, uri: str, user: str, password: str, database: str = "neo4j") -> bool:
    #     """
    #     Set Neo4j connection configuration.
        
    #     Args:
    #         uri: Neo4j URI (e.g., bolt://localhost:7687)
    #         user: Neo4j username
    #         password: Neo4j password
    #         database: Neo4j database name
            
    #     Returns:
    #         True if successful, False otherwise
    #     """
    #     with self._lock:
    #         try:
    #             self.neo4j_uri = uri
    #             self.neo4j_user = user
    #             self.neo4j_password = password
    #             self.neo4j_database = database
                
    #             # Save configuration
    #             self._save_neo4j_config()
                
    #             # Close existing connection if any
    #             if self.driver:
    #                 self.driver.close()
    #                 self.driver = None
    #                 self.index_builder = None
    #                 self.index_provider = None
                
    #             return True
                
    #         except Exception as e:
    #             logger.error(f"Failed to set Neo4j configuration: {e}")
    #             return False
    
    # def cleanup(self):
    #     """Clean up resources."""
    #     with self._lock:
    #         self._cleanup()

    # def _cleanup(self):
    #     if self.driver:
    #         self.driver.close()
            
    #     self.project_path = None
    #     self.neo4j_uri = None
    #     self.neo4j_user = None
    #     self.neo4j_password = None
    #     self.neo4j_database = "neo4j"
    #     self.driver = None
    #     self.index_builder = None
    #     self.index_provider = None
    #     self.config_path = None
            
    #     logger.info("Cleaned up Neo4j Index Manager")


# Global instance
_neo4j_index_manager = Neo4jIndexManager()


def get_neo4j_index_manager() -> Neo4jIndexManager:
    """Get the global Neo4j index manager instance."""
    return _neo4j_index_manager
