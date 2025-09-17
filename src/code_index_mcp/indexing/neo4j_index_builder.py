"""
Neo4j Index Builder - Implementation using Strategy pattern.

This implements a Neo4j-based index builder using the Strategy pattern
for language parsing, similar to the JSON index builder.
"""

import logging
import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any

from neo4j import GraphDatabase

from .strategies import StrategyFactory
from .models import SymbolInfo, FileInfo

logger = logging.getLogger(__name__)


@dataclass
class Neo4jIndexMetadata:
    """Metadata for the Neo4j index."""
    project_path: str
    indexed_files: int
    index_version: str
    timestamp: str
    languages: List[str]
    total_symbols: int = 0
    specialized_parsers: int = 0
    fallback_files: int = 0


class Neo4jIndexBuilder:
    """
    Neo4j-based index builder using Strategy pattern for language parsing.
    
    This class orchestrates the index building process by:
    1. Discovering files in the project
    2. Using StrategyFactory to get appropriate parsers
    3. Extracting symbols and metadata
    4. Building a Neo4j graph representation
    """

    def __init__(self, project_path: str, neo4j_uri: str, neo4j_user: str, neo4j_password: str, 
                 neo4j_database: str = "neo4j", additional_excludes: Optional[List[str]] = None):
        from ..utils import FileFilter
        
        # Input validation
        if not isinstance(project_path, str):
            raise ValueError(f"Project path must be a string, got {type(project_path)}")
        
        project_path = project_path.strip()
        if not project_path:
            raise ValueError("Project path cannot be empty")
            
        if not os.path.isdir(project_path):
            raise ValueError(f"Project path does not exist: {project_path}")
        
        self.project_path = project_path
        self.strategy_factory = StrategyFactory()
        self.file_filter = FileFilter(additional_excludes)
        self.in_memory_index = None

        # Neo4j connection
        self.neo4j_uri = neo4j_uri
        self.neo4j_user = neo4j_user
        self.neo4j_password = neo4j_password
        self.neo4j_database = neo4j_database
        self.driver = GraphDatabase.driver(
            neo4j_uri, 
            auth=(neo4j_user, neo4j_password),
            database=neo4j_database
        )
        
        # Test connection
        try:
            with self.driver.session() as session:
                session.run("RETURN 1")
            logger.info(f"Connected to Neo4j at {neo4j_uri}")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            raise
        
        logger.info(f"Initialized Neo4j index builder for {project_path}")
        strategy_info = self.strategy_factory.get_strategy_info()
        logger.info(f"Available parsing strategies: {len(strategy_info)} types")

        # Log specialized vs fallback coverage
        specialized = len(self.strategy_factory.get_specialized_extensions())
        fallback = len(self.strategy_factory.get_fallback_extensions())
        logger.info(f"Specialized parsers: {specialized} extensions, Fallback coverage: {fallback} extensions")

    def _mark_cross_file_calls(self):
        """Mark relationships that cross file boundaries."""
        with self.driver.session() as session:
            session.run("""
                MATCH (caller_file:File)-[:CONTAINS]->(caller:Symbol)-[:CALLS]->(called:Symbol)<-[:CONTAINS]-(called_file:File)
                WHERE caller_file.path <> called_file.path
                SET caller.has_cross_file_calls = true
                SET called.called_from_other_files = true
            """)
            
    def _validate_cross_file_calls(self):
        """Validate that cross-file calls are being captured."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (caller_file:File)-[:CONTAINS]->(caller:Symbol)-[:CALLS]->(called:Symbol)<-[:CONTAINS]-(called_file:File)
                WHERE caller_file.path <> called_file.path
                RETURN count(*) as cross_file_calls
            """)
            
            record = result.single()
            cross_file_calls = record["cross_file_calls"] if record else 0
            
            logger.info(f"Detected {cross_file_calls} cross-file function calls")
            
            if cross_file_calls == 0:
                logger.warning("No cross-file function calls detected. This is unusual for a real-world codebase.")
                
                # Log some examples of functions that should have cross-file calls
                examples = session.run("""
                    MATCH (f:File)-[:CONTAINS]->(s:Symbol:Function)
                    WHERE s.name IN ['main', 'init', 'get', 'process', 'handle']
                    RETURN s.qualified_name, f.path
                    LIMIT 10
                """)
                
                logger.info("Potential functions that might have cross-file calls:")
                for record in examples:
                    logger.info(f"  - {record['s.qualified_name']} in {record['f.path']}")
    
    def build_index(self, run_clustering=True, k=5) -> bool:
        """
        Build the complete index using Strategy pattern and Neo4j.
        
        Args:
            run_clustering: Whether to run K-means clustering (default: True)
            k: Number of clusters for K-means (default: 5)
            
        Returns:
            True if successful, False otherwise
        """
        logger.info("Building Neo4j index using Strategy pattern...")
        start_time = time.time()

        languages = set()
        specialized_count = 0
        fallback_count = 0
        total_symbols = 0
        total_files = 0

        # Get specialized extensions for tracking
        specialized_extensions = set(self.strategy_factory.get_specialized_extensions())
        
        try:
            # Clear existing index
            self._clear_existing_index()
            
            # Create constraints and indexes
            self._create_schema_constraints()

            # Traverse project files
            not_added = []
            for file_path in self._get_supported_files():
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()

                    ext = Path(file_path).suffix.lower()

                    # Convert to relative path first
                    rel_path = os.path.relpath(file_path, self.project_path).replace('\\', '/')

                    # Get appropriate strategy
                    strategy = self.strategy_factory.get_strategy(ext)

                    # Track strategy usage
                    if ext in specialized_extensions:
                        specialized_count += 1
                    else:
                        fallback_count += 1

                    # Parse file using strategy with relative path
                    symbols, file_info = strategy.parse_file(rel_path, content, self.project_path)
                    
                    # Add file to Neo4j
                    self._add_file_to_neo4j(file_info)
                    
                    # Add symbols to Neo4j
                    _not_added = []
                    for symbol_id, symbol_info in not_added:
                        if symbol_info.file in file_info.file_path:
                            self._add_symbol_to_neo4j(symbol_id, symbol_info, file_info)
                            total_symbols += 1
                        else:
                            _not_added.append((symbol_id, symbol_info))
                    not_added = _not_added
                    for symbol_id, symbol_info in symbols.items():
                        if symbol_info.file in file_info.file_path:
                            self._add_symbol_to_neo4j(symbol_id, symbol_info, file_info)
                            total_symbols += 1
                        else:
                            not_added.append((symbol_id, symbol_info))

                    languages.add(file_info.language)
                    total_files += 1

                    logger.debug(f"Parsed {rel_path}: {len(symbols)} symbols ({file_info.language})")

                except Exception as e:
                    logger.warning(f"Error processing {file_path}: {e}")
            
            new_files = set()
            for symbol_id, symbol_info in not_added:
                file_info = FileInfo(symbol_info.file, "python", line_count=0,symbols={}, imports=[])
                self._add_symbol_to_neo4j(symbol_id, symbol_info, file_info)
                total_symbols += 1
                new_files.add(symbol_info.file)
            total_files += len(new_files)
            
            # Mark cross-file calls
            self._mark_cross_file_calls()
            
            # Validate cross-file calls
            self._validate_cross_file_calls()
            
            # After building the index, compute features and run clustering if requested
            if run_clustering:
                logger.info("Computing features and running clustering...")
                self._compute_function_features()
                self._run_kmeans_clustering(k=k)
                
                # Update metadata to include clustering information
                clustering_metadata = {
                    "clustering_k": k,
                    "clustering_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                }
            else:
                clustering_metadata = {}

            # Store index metadata
            metadata = Neo4jIndexMetadata(
                project_path=self.project_path,
                indexed_files=total_files,
                index_version="1.0.0-neo4j",
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                languages=sorted(list(languages)),
                total_symbols=total_symbols,
                specialized_parsers=specialized_count,
                fallback_files=fallback_count
            )
            metadata_dict = asdict(metadata)
            metadata_dict.update(clustering_metadata)
            self._store_index_metadata(metadata_dict)

            elapsed = time.time() - start_time
            logger.info(f"Built index with {total_symbols} symbols from {total_files} files in {elapsed:.2f}s")
            logger.info(f"Languages detected: {sorted(languages)}")
            logger.info(f"Strategy usage: {specialized_count} specialized, {fallback_count} fallback")

            return True
            
        except Exception as e:
            logger.error(f"Error building Neo4j index: {e}")
            return False

    def _clear_existing_index(self):
        """Clear the existing Neo4j index."""
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
        logger.info("Cleared existing Neo4j index")

    def _create_schema_constraints(self):
        """Create Neo4j schema constraints and indexes."""
        with self.driver.session() as session:
            # Create constraints
            session.run("CREATE CONSTRAINT file_path IF NOT EXISTS FOR (f:File) REQUIRE f.path IS UNIQUE")
            session.run("CREATE CONSTRAINT symbol_qualified_name IF NOT EXISTS FOR (s:Symbol) REQUIRE s.qualified_name IS UNIQUE")
            
            # Create indexes
            session.run("CREATE INDEX file_language IF NOT EXISTS FOR (f:File) ON (f.language)")
            session.run("CREATE INDEX symbol_name IF NOT EXISTS FOR (s:Symbol) ON (s.name)")
            
            # Create fulltext index for search
            try:
                session.run("CREATE FULLTEXT INDEX symbol_search IF NOT EXISTS FOR (s:Symbol) ON EACH [s.name, s.signature, s.docstring]")
            except Exception as e:
                logger.warning(f"Could not create fulltext index (may require Enterprise Edition): {e}")
        
        logger.info("Created Neo4j schema constraints and indexes")

    def _add_file_to_neo4j(self, file_info: FileInfo):
        """Add a file to the Neo4j database."""
        with self.driver.session() as session:
            # Create file node
            session.run("""
                MERGE (f:File {path: $path})
                SET f.language = $language,
                    f.line_count = $line_count
            """, {
                "path": file_info.file_path,
                "language": file_info.language,
                "line_count": file_info.line_count
            })
            
            # Add imports as properties
            if file_info.imports:
                session.run("""
                    MATCH (f:File {path: $path})
                    SET f.imports = $imports
                """, {
                    "path": file_info.file_path,
                    "imports": file_info.imports
                })
            
            # Add exports as properties
            if file_info.exports:
                session.run("""
                    MATCH (f:File {path: $path})
                    SET f.exports = $exports
                """, {
                    "path": file_info.file_path,
                    "exports": file_info.exports
                })

    def _add_symbol_to_neo4j(self, symbol_id: str, symbol_info: SymbolInfo, file_info: FileInfo):
        """Add a symbol to the Neo4j database."""
        with self.driver.session() as session:
            # Create symbol node
            session.run("""
                MERGE (f:File {path: $path})
            """, {"path": file_info.file_path})
            session.run("""
                MERGE (f:File {path: $path})
            """, {"path": symbol_info.file})
            session.run("""
                MERGE (s:Symbol {qualified_name: $qualified_name})
                SET s.name = $name,
                    s.type = $type,
                    s.line = $line,
                    s.signature = $signature,
                    s.docstring = $docstring
                WITH s
                MATCH (f:File {path: $file_path})
                MERGE (f)-[:CONTAINS]->(s)
                WITH s
                MATCH (f:File {path: $path})
                MERGE (f)-[:CONTAINS]->(s)
            """, {
                "qualified_name": symbol_id,
                "name": symbol_id.split("::")[-1],
                "type": symbol_info.type,
                "line": symbol_info.line,
                "signature": symbol_info.signature,
                "docstring": symbol_info.docstring,
                "file_path": file_info.file_path,
                "path": symbol_info.file
            })
            
            # Add appropriate label based on type
            if symbol_info.type == "class":
                session.run("MATCH (s:Symbol {qualified_name: $id}) SET s:Class", {"id": symbol_id})
            elif symbol_info.type in ["function", "method"]:
                session.run("MATCH (s:Symbol {qualified_name: $id}) SET s:Function", {"id": symbol_id})
            
            # Add relationships for called symbols with improved handling for cross-file calls
            # if hasattr(symbol_info, 'called_symbols') and symbol_info.called_symbols:
            #     for called_symbol in symbol_info.called_symbols:
            #         # Extract file path from called_symbol if present
            #         called_parts = called_symbol.split("::")
            #         if len(called_parts) >= 2 and not called_parts[0] == "external":
            #             called_file_path = "::".join(called_parts[:-1])
            #             called_name = called_parts[-1]
                        
            #             # First ensure the called file exists
            #             session.run("""
            #                 MERGE (f:File {path: $path})
            #             """, {"path": called_file_path})
                        
            #             # Then create the relationship with file context
            #             session.run("""
            #                 MATCH (caller:Symbol {qualified_name: $caller_id})
            #                 MATCH (caller_file:File)-[:CONTAINS]->(caller)
            #                 MERGE (called:Symbol {qualified_name: $called_id})
            #                 MATCH (called_file:File {path: $called_file_path})
            #                 MERGE (called_file)-[:CONTAINS]->(called)
            #                 MERGE (caller)-[:CALLS]->(called)
            #                 SET caller.has_external_calls = true
            #                 SET called.called_from_external = true
            #             """, {
            #                 "caller_id": symbol_id,
            #                 "called_id": called_symbol,
            #                 "called_file_path": called_file_path
            #             })
            #         else:
            #             # Handle same-file or unresolved external calls
            #             session.run("""
            #                 MATCH (caller:Symbol {qualified_name: $caller_id})
            #                 MERGE (called:Symbol {qualified_name: $called_id})
            #                 MERGE (caller)-[:CALLS]->(called)
            #             """, {
            #                 "caller_id": symbol_id,
            #                 "called_id": called_symbol
            #             })
            
            # Add relationships for symbols that call this symbol
            if symbol_info.called_by:
                for caller_id in symbol_info.called_by:
                    session.run("""
                        MATCH (called:Symbol {qualified_name: $called_id})
                        MERGE (caller:Symbol {qualified_name: $caller_id})
                        MERGE (caller)-[:CALLS]->(called)
                    """, {
                        "called_id": symbol_id,
                        "caller_id": caller_id
                    })

    def _store_index_metadata(self, metadata: Dict[str, Any]):
        """Store index metadata in Neo4j."""
        with self.driver.session() as session:
            session.run("""
                CREATE (m:IndexMetadata)
                SET m = $metadata
            """, {"metadata": metadata})
        logger.info("Stored index metadata in Neo4j")

    def _get_supported_files(self) -> List[str]:
        """
        Get all supported files in the project using centralized filtering.

        Returns:
            List of file paths that can be parsed
        """
        supported_files = []
        base_path = Path(self.project_path)

        try:
            for root, dirs, files in os.walk(self.project_path):
                # Filter directories in-place using centralized logic
                dirs[:] = [d for d in dirs if not self.file_filter.should_exclude_directory(d)]

                # Filter files using centralized logic
                for file in files:
                    file_path = Path(root) / file
                    if self.file_filter.should_process_path(file_path, base_path):
                        supported_files.append(str(file_path))

        except Exception as e:
            logger.error(f"Error scanning directory {self.project_path}: {e}")

        logger.debug(f"Found {len(supported_files)} supported files")
        return supported_files

    def get_file_symbols(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Get symbols for a specific file.

        Args:
            file_path: Relative path to the file

        Returns:
            List of symbols in the file
        """
        try:
            # Normalize file path
            file_path = file_path.replace('\\', '/')
            if file_path.startswith('./'):
                file_path = file_path[2:]

            with self.driver.session() as session:
                result = session.run("""
                    MATCH (f:File {path: $path})-[:CONTAINS]->(s:Symbol)
                    OPTIONAL MATCH (s)-[:CALLS]->(called:Symbol)
                    RETURN s.qualified_name as id, s.name as name, s.type as type, 
                           s.line as line, s.signature as signature, s.docstring as docstring,
                           collect(distinct called.qualified_name) as called_symbols
                    ORDER BY s.line
                """, {"path": file_path})
                
                symbols = []
                for record in result:
                    symbols.append({
                        "id": record["id"],
                        "name": record["name"],
                        "type": record["type"],
                        "line": record["line"],
                        "signature": record["signature"],
                        "docstring": record["docstring"],
                        "called_symbols": record["called_symbols"]
                    })
                
                return symbols

        except Exception as e:
            logger.error(f"Error getting file symbols for {file_path}: {e}")
            return []

    def search_symbols(self, query: str, symbol_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search for symbols by name or content.

        Args:
            query: Search query
            symbol_type: Optional type filter (class, function, etc.)

        Returns:
            List of matching symbols
        """
        try:
            with self.driver.session() as session:
                if symbol_type:
                    result = session.run("""
                        MATCH (s:Symbol)
                        WHERE s.type = $type AND (s.name CONTAINS $query OR s.signature CONTAINS $query OR s.docstring CONTAINS $query)
                        RETURN s.qualified_name as id, s.name as name, s.type as type, 
                               s.line as line, s.signature as signature, s.docstring as docstring
                        LIMIT 50
                    """, {"query": query, "type": symbol_type})
                else:
                    result = session.run("""
                        MATCH (s:Symbol)
                        WHERE s.name CONTAINS $query OR s.signature CONTAINS $query OR s.docstring CONTAINS $query
                        RETURN s.qualified_name as id, s.name as name, s.type as type, 
                               s.line as line, s.signature as signature, s.docstring as docstring
                        LIMIT 50
                    """, {"query": query})
                
                symbols = []
                for record in result:
                    symbols.append({
                        "id": record["id"],
                        "name": record["name"],
                        "type": record["type"],
                        "line": record["line"],
                        "signature": record["signature"],
                        "docstring": record["docstring"]
                    })
                
                return symbols

        except Exception as e:
            logger.error(f"Error searching symbols: {e}")
            return []

    def get_symbol_callers(self, symbol_name: str) -> List[str]:
        """
        Get all symbols that call the given symbol.

        Args:
            symbol_name: Qualified name of the symbol

        Returns:
            List of qualified names of symbols that call the given symbol
        """
        try:
            with self.driver.session() as session:
                result = session.run("""
                    MATCH (caller:Symbol)-[:CALLS]->(called:Symbol {qualified_name: $symbol_name})
                    RETURN caller.qualified_name as caller_id
                """, {"symbol_name": symbol_name})
                
                return [record["caller_id"] for record in result]

        except Exception as e:
            logger.error(f"Error getting symbol callers: {e}")
            return []

    def get_symbol_dependencies(self, symbol_name: str) -> Dict[str, List[str]]:
        """
        Get dependencies for a symbol (both callers and called).

        Args:
            symbol_name: Qualified name of the symbol

        Returns:
            Dictionary with callers and called symbols
        """
        try:
            with self.driver.session() as session:
                # Get symbols called by this symbol
                called_result = session.run("""
                    MATCH (caller:Symbol {qualified_name: $symbol_name})-[:CALLS]->(called:Symbol)
                    RETURN called.qualified_name as called_id
                """, {"symbol_name": symbol_name})
                
                called = [record["called_id"] for record in called_result]
                
                # Get symbols that call this symbol
                caller_result = session.run("""
                    MATCH (caller:Symbol)-[:CALLS]->(called:Symbol {qualified_name: $symbol_name})
                    RETURN caller.qualified_name as caller_id
                """, {"symbol_name": symbol_name})
                
                callers = [record["caller_id"] for record in caller_result]
                
                return {
                    "callers": callers,
                    "called": called
                }

        except Exception as e:
            logger.error(f"Error getting symbol dependencies: {e}")
            return {"callers": [], "called": []}

    def _compute_function_features(self):
        """Compute numerical features for all Function nodes in the graph."""
        logger.info("Computing function features for clustering...")
        
        with self.driver.session() as session:
            # Count outgoing calls for each function
            session.run("""
                MATCH (f:Function)-[:CALLS]->(other)
                WITH f, count(other) as outgoing_calls
                SET f.outgoing_calls = outgoing_calls
            """)
            
            # Count incoming calls for each function
            session.run("""
                MATCH (f:Function)<-[:CALLS]-(other)
                WITH f, count(other) as incoming_calls
                SET f.incoming_calls = incoming_calls
            """)
            
            # Set default values of 0 for functions with no calls
            session.run("""
                MATCH (f:Function)
                WHERE f.outgoing_calls IS NULL
                SET f.outgoing_calls = 0
            """)
            
            session.run("""
                MATCH (f:Function)
                WHERE f.incoming_calls IS NULL
                SET f.incoming_calls = 0
            """)
            
            # Count arguments for each function
            session.run("""
                MATCH (f:Function)
                WHERE f.signature IS NOT NULL
                SET f.arg_count = CASE true
                  WHEN f.type = "file" THEN 0
                  WHEN f.signature CONTAINS "():" THEN 0
                  WHEN f.signature CONTAINS "," THEN size(split(f.signature, ","))
                  ELSE 1
                END
            """)
            
            # Add file properties to functions
            session.run("""
                MATCH (file:File)-[:CONTAINS]->(f:Function)
                SET f.file_line_count = CASE WHEN file.line_count IS NOT NULL THEN file.line_count ELSE 0 END,
                    f.file_import_count = CASE WHEN file.imports IS NOT NULL THEN size(file.imports) ELSE 0 END
            """)
            
            # Create graph projection for GDS
            session.run("""
                CALL gds.graph.project(
                    'code-functions', {
                        Function: { label: 'Function' }
                    },
                    {
                    ALL_CALLS: { type: 'CALLS',
                            orientation: 'UNDIRECTED'
                        }
                    }
                )
                YIELD graphName, nodeCount, relationshipCount
            """)
            
            # Create embedding vector for clustering
            session.run("""
                CALL gds.fastRP.write('code-functions',
                {
                    embeddingDimension: 10,
                    writeProperty: 'embedding'
                    }
                )
            """)
            session.run("CALL gds.graph.drop('code-functions')")
            # session.run("""
            #     MATCH (f:Function)
            #     SET f.embedding = [
            #       toFloat(f.outgoing_calls), 
            #       toFloat(f.incoming_calls), 
            #       toFloat(f.arg_count),
            #       toFloat(f.file_line_count),
            #       toFloat(f.file_import_count)
            #     ]
            # """)
            
            logger.info("Function features computed successfully")
    
    def _run_kmeans_clustering(self, k=5, max_iterations=35, random_seed=42):
        """
        Run K-means clustering on Function nodes using computed features.
        
        Args:
            k: Number of clusters (default: 5)
            max_iterations: Maximum number of iterations (default: 50)
            random_seed: Random seed for reproducibility (default: 42)
        """
        logger.info(f"Running K-means clustering with k={k}...")
        
        try:
            with self.driver.session() as session:
                # Check if GDS library is installed
                try:
                    session.run("CALL gds.list()")
                except Exception as e:
                    logger.error(f"Neo4j Graph Data Science library not installed or not accessible: {e}")
                    return False
                
                # Check if graph projection exists and drop it if it does
                result = session.run("CALL gds.graph.exists('code-functions') YIELD exists")
                if result.single()["exists"]:
                    session.run("CALL gds.graph.drop('code-functions')")
                
                # Create graph projection for GDS
                session.run("""
                    CALL gds.graph.project(
                      'code-functions',
                      'Function',
                      {
                        CALLS: {
                          orientation: 'NATURAL'
                        }
                      },
                      {
                        nodeProperties: ['embedding']
                      }
                    )
                """)
                
                # Run K-means clustering with correct output parameters
                result = session.run(f"""
                    CALL gds.kmeans.write('code-functions', {{
                      nodeProperty: 'embedding', 
                      k: {k}, 
                      maxIterations: {max_iterations}, 
                      randomSeed: {random_seed}, 
                      writeProperty: 'cluster',
                      computeSilhouette: true
                    }})
                    YIELD nodePropertiesWritten, computeMillis, configuration
                    RETURN nodePropertiesWritten, computeMillis, configuration
                """)
                
                record = result.single()
                if record:
                    logger.info(f"K-means clustering completed: {record['nodePropertiesWritten']} nodes written in {record['computeMillis']}ms")
                
                # Compute cluster statistics
                self._compute_cluster_statistics()
                
                # Drop graph projection to free memory
                session.run("CALL gds.graph.drop('code-functions')")
                
                return True
        except Exception as e:
            logger.error(f"Error running K-means clustering: {e}")
            return False
    
    def _compute_cluster_statistics(self):
        """Compute and store statistics for each cluster."""
        logger.info("Computing cluster statistics...")
        
        with self.driver.session() as session:
            # Create a ClusterStatistics node if it doesn't exist
            session.run("""
                MERGE (stats:ClusterStatistics {id: 'cluster_stats'})
            """)
            
            # Compute cluster statistics
            result = session.run("""
                MATCH (f:Function)
                WHERE f.cluster IS NOT NULL
                WITH f as f,
                     f.cluster as cluster,
                     avg(f.outgoing_calls) as avg_outgoing,
                     avg(f.incoming_calls) as avg_incoming,
                     avg(f.arg_count) as avg_args,
                     avg(f.file_line_count) as avg_lines,
                     avg(f.file_import_count) as avg_imports,
                     count(*) as count
                MERGE (c:Cluster {id: cluster})
                SET c.count = count,
                    c.avg_outgoing_calls = avg_outgoing,
                    c.avg_incoming_calls = avg_incoming,
                    c.avg_args = avg_args,
                    c.avg_file_lines = avg_lines,
                    c.avg_file_imports = avg_imports,
                    f:$(toString(f.cluster))
                WITH c, f
                MATCH (stats:ClusterStatistics {id: 'cluster_stats'})
                MERGE (stats)-[:HAS_CLUSTER]->(c)
                MERGE (f)-[:HAS_CLUSTER]->(c)
                RETURN c.id, c.count
            """)
            
            clusters = [f"Cluster {record['c.id']}: {record['c.count']} functions" 
                       for record in result]
            
            logger.info(f"Computed statistics for {len(clusters)} clusters")
            logger.info(f"Clusters: {', '.join(clusters)}")
    
    def close(self):
        """Close the Neo4j driver."""
        if self.driver:
            self.driver.close()
            logger.info("Closed Neo4j driver")
