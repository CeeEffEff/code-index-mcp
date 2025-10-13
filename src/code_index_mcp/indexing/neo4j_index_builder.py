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

from mcp import ServerSession
from mcp.server.fastmcp import Context
from neo4j import GraphDatabase

from .strategies import StrategyFactory
from .models import SymbolInfo, FileInfo, ImportCallInfo
from .utils.symbol_id_normalizer import SymbolIDNormalizer

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
    venv: Optional[str] = None


class Neo4jIndexBuilder:
    """
    Neo4j-based index builder using Strategy pattern for language parsing.

    This class orchestrates the index building process by:
    1. Discovering files in the project
    2. Using StrategyFactory to get appropriate parsers
    3. Extracting symbols and metadata
    4. Building a Neo4j graph representation
    """

    def __init__(
        self,
        project_path: str,
        neo4j_uri: str,
        neo4j_user: str,
        neo4j_password: str,
        neo4j_database: str = "neo4j",
        additional_excludes: Optional[List[str]] = None,
        venv_path: str = None,
        
    ):
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
        self.venv_path = venv_path if venv_path else None
        self.strategy_factory = StrategyFactory()
        self.file_filter = FileFilter(additional_excludes)
        self.in_memory_index = None
        
        # Initialize SymbolIDNormalizer for consistent cross-file symbol IDs
        self.normalizer = SymbolIDNormalizer(
            project_root=project_path,
            venv_root=venv_path
        )
        self.normalizer = None

        # Neo4j connection
        self.neo4j_uri = neo4j_uri
        self.neo4j_user = neo4j_user
        self.neo4j_password = neo4j_password
        self.neo4j_database = neo4j_database
        self.driver = GraphDatabase.driver(
            neo4j_uri, auth=(neo4j_user, neo4j_password), database=neo4j_database
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
        logger.info(
            f"Specialized parsers: {specialized} extensions, Fallback coverage: {fallback} extensions"
        )

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
                logger.debug(
                    "No cross-file function calls detected. This is unusual for a real-world codebase."
                )

                # Log some examples of functions that should have cross-file calls
                examples = session.run("""
                    MATCH (f:File)-[:CONTAINS]->(s:Symbol:Function)
                    WHERE s.name IN ['main', 'init', 'get', 'process', 'handle']
                    RETURN s.qualified_name, f.path
                    LIMIT 10
                """)

                logger.info("Potential functions that might have cross-file calls:")
                for record in examples:
                    logger.info(
                        f"  - {record['s.qualified_name']} in {record['f.path']}"
                    )

    def build_index(self, run_clustering=True, k=5, max_iterations=50, ctx: Context[ServerSession, object] = None) -> bool:
        """
        Build the complete index using Strategy pattern and Neo4j.

        Args:
            run_clustering: Whether to run K-means clustering (default: True)
            k: Number of clusters for K-means (default: 5)
            max_iterations: Maximum number of iterations for K-means (default: 50)

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
            import_calls: Dict[str, Dict[str, ImportCallInfo]] = {}
            num_steps = len(files:=self._get_supported_files()) + (1 if run_clustering else 0)
            for file_num, file_path in enumerate(files):
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()

                    ext = Path(file_path).suffix.lower()

                    # Convert to relative path first
                    rel_path = os.path.relpath(file_path, self.project_path).replace(
                        "\\", "/"
                    )

                    # Get appropriate strategy
                    strategy = self.strategy_factory.get_strategy(ext)

                    # Track strategy usage
                    if ext in specialized_extensions:
                        specialized_count += 1
                    else:
                        fallback_count += 1

                    # Parse file using strategy with relative path and normalizer
                    symbols, file_info = strategy.parse_file(
                        rel_path, content, self.project_path, self.venv_path,
                        # normalizer=self.normalizer
                    )

                    # Add file to Neo4j
                    self._add_file_to_neo4j(file_info)

                    for symbol_id, symbol_info in symbols.items():
                        self._add_symbol_to_neo4j(symbol_id, symbol_info, file_info)

                    languages.add(file_info.language)
                    total_files += 1

                    if file_info.import_calls:
                        num_steps += 1
                        import_calls[file_info.file_path] = file_info.import_calls
                    logger.debug(
                        f"Parsed {rel_path}: {len(symbols)} symbols ({file_info.language})"
                    )

                except Exception as e:
                    logger.exception(f"Error processing {file_path}: {e}")
                # finally:
                #     ctx.report_progress(file_num, num_steps)

            logger.info(f"Adding {len(import_calls)=}")
            logger.debug(f"{import_calls=}")
            parsed_modules = set()
            m, c, f = {},{},{}
            for import_file_num, (file_path, file_import_calls) in enumerate(import_calls.items()):
                # Add all files
                # Add all symbols
                # Try to link
                for import_call_info in file_import_calls.values():
                    if (module_path := import_call_info.import_spec.spec.origin) not in parsed_modules:
                        import_call_info.import_spec._getmembers()
                        m.update(import_call_info.import_spec.methods)
                        c.update(import_call_info.import_spec.classes)
                        f.update(import_call_info.import_spec.functions)
                        parsed_modules.add(module_path)
                        total_files += 1
                    else:
                        import_call_info.import_spec._classes = c
                        import_call_info.import_spec._functions = f
                        import_call_info.import_spec._methods = m
                    import_call_info.called_symbol_info.type = import_call_info.import_spec.try_get_symbol_type(import_call_info.called_symbol_id) or "function"
                    self._add_import_call_to_neo4j(file_path, import_call_info)
                # ctx.report_progress(file_num+import_file_num, num_steps)
            # Mark cross-file calls
            # self._mark_cross_file_calls()

            # Validate cross-file calls
            # self._validate_cross_file_calls()

            # After building the index, compute features and run clustering if requested
            if run_clustering:
                clustering_metadata = self.run_kmeans_clustering(k, max_iterations)
            else:
                clustering_metadata = {}
            # ctx.report_progress(num_steps, num_steps)
            # Store index metadata
            metadata = Neo4jIndexMetadata(
                project_path=self.project_path,
                venv=self.venv_path,
                indexed_files=total_files,
                index_version="1.0.0-neo4j",
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                languages=sorted(list(languages)),
                total_symbols=total_symbols,
                specialized_parsers=specialized_count,
                fallback_files=fallback_count,
            )
            metadata_dict = asdict(metadata)
            metadata_dict.update(clustering_metadata)
            self._store_index_metadata(metadata_dict)

            elapsed = time.time() - start_time
            logger.info(
                f"Built index with {total_symbols} symbols from {total_files} files in {elapsed:.2f}s"
            )
            logger.info(f"Languages detected: {sorted(languages)}")
            logger.info(
                f"Strategy usage: {specialized_count} specialized, {fallback_count} fallback"
            )

            return True

        except Exception as e:
            logger.exception(f"Error building Neo4j index: {e}")
            return False

    def run_kmeans_clustering(self, k, max_iterations, embedding_dimensions=20):
        logger.info("Computing features and running clustering...")
        self._compute_features(embedding_dimensions)
        self._run_kmeans_clustering(max_iterations=max_iterations, k=k)

        # Update metadata to include clustering information
        return {
            "clustering_k": k,
            "max_iterations": max_iterations,
            "embedding_dimensions": embedding_dimensions,
            "clustering_timestamp": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
            ),
        }

    def _clear_existing_index(self):
        """Clear the existing Neo4j index."""
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
        logger.info("Cleared existing Neo4j index")

    def _create_schema_constraints(self):
        """Create Neo4j schema constraints and indexes."""
        with self.driver.session() as session:
            # Create constraints
            session.run(
                "CREATE CONSTRAINT file_path IF NOT EXISTS FOR (f:File) REQUIRE f.path IS UNIQUE"
            )
            session.run(
                "CREATE CONSTRAINT symbol_qualified_name IF NOT EXISTS FOR (s:Symbol) REQUIRE s.qualified_name IS UNIQUE"
            )

            # Create indexes
            session.run(
                "CREATE INDEX file_language IF NOT EXISTS FOR (f:File) ON (f.language)"
            )
            session.run(
                "CREATE INDEX symbol_name IF NOT EXISTS FOR (s:Symbol) ON (s.name)"
            )

            # Create fulltext index for search
            try:
                session.run(
                    "CREATE FULLTEXT INDEX symbol_search IF NOT EXISTS FOR (s:Symbol) ON EACH [s.name, s.signature, s.docstring]"
                )
            except Exception as e:
                logger.warning(
                    f"Could not create fulltext index (may require Enterprise Edition): {e}"
                )

        logger.info("Created Neo4j schema constraints and indexes")

    def _add_file_to_neo4j(self, file_info: FileInfo):
        """Add a file to the Neo4j database."""
        with self.driver.session() as session:
            # Create file node
            session.run(
                """
                MERGE (f:File {path: $path})
                SET f.language = $language,
                    f.line_count = $line_count
            """,
                {
                    "path": file_info.file_path,
                    "language": file_info.language,
                    "line_count": file_info.line_count,
                },
            )

            # Add imports as properties
            if file_info.imports:
                session.run(
                    """
                    MATCH (f:File {path: $path})
                    SET f.imports = $imports
                """,
                    {"path": file_info.file_path, "imports": file_info.imports},
                )

            # Add exports as properties
            if file_info.exports:
                session.run(
                    """
                    MATCH (f:File {path: $path})
                    SET f.exports = $exports
                """,
                    {"path": file_info.file_path, "exports": file_info.exports},
                )
            # for import_call in file_info.import_calls:
            #     self._add_file_to_neo4j()
                

    def _add_symbol_to_neo4j(
        self, symbol_id: str, symbol_info: SymbolInfo, file_info: FileInfo
    ):
        """Add a symbol to the Neo4j database using MERGE to avoid constraint violations."""
        with self.driver.session() as session:
            # Create or match the file node
            session.run(
                """
                MERGE (f:File {path: $path})
                SET f.language = $language,
                    f.line_count = $line_count
            """,
                {
                    "path": symbol_info.file,
                    "language": file_info.language,
                    "line_count": file_info.line_count,
                },
            )

            # Create or match the symbol node
            session.run(
                """
                MERGE (s:Symbol {qualified_name: $qualified_name})
                SET s.name = $name,
                    s.type = $type,
                    s.line = $line,
                    s.signature = $signature,
                    s.docstring = $docstring,
                    s.call_depths = $call_depths,
                    s.decorator_list = $decorator_list
                WITH s
                MATCH (f:File {path: $path})
                MERGE (f)-[:CONTAINS]->(s)
            """,
                {
                    "qualified_name": symbol_id,
                    "name": symbol_id.split("::")[-1],
                    "type": symbol_info.type,
                    "line": symbol_info.line,
                    "signature": symbol_info.signature,
                    "docstring": symbol_info.docstring,
                    "path": symbol_info.file,
                    "call_depths": list(symbol_info.stack_levels),
                    "decorator_list": symbol_info.decorator_list,
                },
            )

            # # Add appropriate label based on type
            # session.run(
            #     "MERGE (s:Symbol {qualified_name: $id})",
            #     {"id": symbol_id},
            # )
            if symbol_info.type == "class":
                session.run(
                    """
                    MATCH (s:Symbol {qualified_name: $qualified_name})
                    SET s:Class
                    """,
                    {"qualified_name": symbol_id},
                )
            elif symbol_info.type == "function":
                session.run(
                    
                    """
                    MATCH (s:Symbol {qualified_name: $qualified_name})
                    SET s:Function
                    """,
                    {"qualified_name": symbol_id},
                )
            elif symbol_info.type == "method":
                [symbol_path, symbol_name] = symbol_id.split("::")
                class_id = f"{symbol_path}::{symbol_name.split('.')[0]}"
                # Needs doing last
                session.run(
                    """
                    MATCH (s:Symbol {qualified_name: $qualified_name})
                    SET s:Function
                    WITH s
                    MERGE (c:Class {qualified_name: $cid})
                    MERGE (c)-[:HAS_METHOD]->(s)
                    MERGE (c)<-[:CLASS_TYPE]-(s)
                    """,
                    {"cid": class_id, "qualified_name": symbol_id},
                )
                session.run(
                    """
                    MATCH (c:Class {qualified_name: $cid})
                    MATCH (f:File {path: $path})
                    MERGE (f)-[:CONTAINS]->(c)
                    """,
                    {"path": symbol_info.file, "cid": class_id},
                )

            # Add relationships for called symbols
            # if symbol_info.called_symbols:
            #     for called_symbol in symbol_info.called_symbols:
            #         called_parts = called_symbol.split("::")
            #         called_file_path = "::".join(called_parts[:-1])
            #         called_name = called_parts[-1]

            #         # Match the called file node
            #         session.run(
            #             """
            #             MERGE (called_file:File {path: $path})
            #         """,
            #             {"path": called_file_path},
            #         )

            #         # Match the called symbol node
            #         session.run(
            #             """
            #             MERGE (called:Symbol {qualified_name: $qualified_name})
            #             WITH called
            #             MATCH (called_file:File {path: $path})
            #             MERGE (called_file)-[:CONTAINS]->(called)
            #             MERGE (s:Symbol {qualified_name: $caller_id})-[:CALLS]->(called)
            #         """,
            #             {
            #                 "caller_id": symbol_id,
            #                 "qualified_name": called_symbol,
            #                 "path": called_file_path,
            #             },
            #         )

            # Add relationships for symbols that call this symbol
            # if symbol_info.called_by:
            for caller_id in symbol_info.called_by:
                session.run(
                    """
                    MATCH (called:Symbol {qualified_name: $called_id})
                    MERGE (caller:Symbol {qualified_name: $caller_id})
                    MERGE (caller)-[:CALLS]->(called)
                """,
                    {"called_id": symbol_id, "caller_id": caller_id},
                )
            for caller_id in symbol_info.decorator_list:
                [caller_path, _] = caller_id.split("::") if "::" in caller_id else ["venv", caller_id]
                session.run(
                    """
                        MERGE (f:File {path: $caller_path})
                        ON CREATE
                        SET f.language = $language
                """,
                    {
                        "caller_path": caller_path,
                        "language": file_info.language,
                    },
                )
                session.run(
                    """
                    MATCH (caller:Symbol {qualified_name: $caller_id})
                    SET caller:Decorater
                """,
                    {"caller_id": caller_id},
                )
                
                session.run(
                    """
                    MATCH (called:Symbol {qualified_name: $called_id})
                    MATCH (caller:Symbol {qualified_name: $caller_id})
                    MATCH (f:File {path: $caller_path})
                    MERGE (caller)-[:DECORATES]->(called)
                    MERGE (f)-[:CONTAINS]->(caller)
                """,
                    {"called_id": symbol_id, "caller_id": caller_id, "caller_path": caller_path},
                )

    def _add_import_call_to_neo4j(self, file_path: str, import_call: ImportCallInfo):
        
        logger.debug(f"Adding import call: {import_call.called_symbol_info.type}-{import_call.called_symbol_id} - {import_call.import_spec.spec}")
        
        import_symbol_info = import_call.called_symbol_info
        import_symbol_id = import_call.called_symbol_id
        with self.driver.session() as session:
            # TODO make same as symbols?
            session.run(  # The file with the imports
                """
                MERGE (f:File {path: $path})
            """,
                {"path": import_call.import_relative_path},
            )
            if import_call.import_relative_path != import_symbol_info.file:
                session.run(  # The file where the imported thing is potentially
                    """
                    MERGE (f:File {path: $path})
                """,
                    {"path": import_symbol_info.file},
                )
            session.run(  # The file where the import is happening
                """
                MERGE (f:File {path: $path})
            """,
                {"path": file_path},
            )
            # Create or match the symbol node
            session.run(
                """
                MERGE (s:Symbol {qualified_name: $qualified_name})
                ON CREATE SET s.name = $name,
                    s.type = $type,
                    s.call_depths = $call_depths,
                    s.decorator_list = $decorator_list,
                    s.imported_by_file_path = $imported_by_file_path
                WITH s
                MATCH (f:File {path: $path})
                MERGE (f)-[:CONTAINS]->(s)
            """,
                {
                    "qualified_name": import_symbol_id,
                    "name": import_symbol_id.split("::")[-1],
                    "type": import_symbol_info.type,
                    "path": import_symbol_info.file,
                    "call_depths": list(import_symbol_info.stack_levels),
                    "decorator_list": import_symbol_info.decorator_list,
                    "imported_by_file_path": file_path
                },
            )
            if import_symbol_info.type == "class":
                session.run(
                    """
                    MATCH (s:Symbol {qualified_name: $qualified_name})
                    SET s:Class
                    """,
                    {"qualified_name": import_symbol_id},
                )
            elif import_symbol_info.type == "function":
                session.run(
                    
                    """
                    MATCH (s:Symbol {qualified_name: $qualified_name})
                    SET s:Function
                    """,
                    {"qualified_name": import_symbol_id},
                )
            elif import_symbol_info.type == "method":
                [symbol_path, symbol_name] = import_symbol_id.split("::")
                class_id = f"{symbol_path}::{symbol_name.split('.')[0]}"
                # Needs doing last
                session.run(
                    """
                    MATCH (s:Symbol {qualified_name: $qualified_name})
                    SET s:Function
                    WITH s
                    MERGE (c:Class {qualified_name: $cid})
                    MERGE (c)-[:HAS_METHOD]->(s)
                    MERGE (c)<-[:CLASS_TYPE]-(s)
                    """,
                    {"cid": class_id, "qualified_name": import_symbol_id},
                )
                session.run(
                    """
                    MERGE (f:File {path: $path})
                    MERGE (c:Class {qualified_name: $cid})
                    MERGE (f)-[:CONTAINS]->(c)
                    """,
                    {"path": import_symbol_info.file, "cid": class_id},
                )

            for caller_id in import_symbol_info.called_by:
                session.run(
                    """
                    MATCH (called:Symbol {qualified_name: $called_id})
                    MERGE (caller:Symbol {qualified_name: $caller_id})
                    MERGE (caller)-[:CALLS]->(called)
                """,
                    {"called_id": import_call.called_symbol_id, "caller_id": caller_id},
                )
            for caller_id in import_symbol_info.decorator_list:
                [caller_path, _] = caller_id.split("::") if "::" in caller_id else ["venv", caller_id]
                session.run(
                    """
                        MERGE (f:File {path: $caller_path})
                """,
                    {
                        "path": caller_path
                    },
                )
                session.run(
                    """
                    MATCH (caller:Symbol {qualified_name: $caller_id})
                    SET caller:Decorater
                """,
                    {"caller_id": caller_id},
                )
                session.run(
                    """
                    MATCH (called:Symbol {qualified_name: $called_id})
                    MERGE (caller:Symbol {qualified_name: $caller_id})
                    MATCH (f:File {path: $caller_path})
                    MERGE (caller)-[:DECORATES]->(called)
                    MERGE (f)-[:CONTAINS]->(caller)
                """,
                    {"called_id": import_call.called_symbol_id, "caller_id": caller_id, "caller_path": caller_path},
                )

    def _store_index_metadata(self, metadata: Dict[str, Any]):
        """Store index metadata in Neo4j."""
        with self.driver.session() as session:
            session.run(
                """
                CREATE (m:IndexMetadata)
                SET m = $metadata
            """,
                {"metadata": metadata},
            )
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
                dirs[:] = [
                    d for d in dirs if not self.file_filter.should_exclude_directory(d)
                ]

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
            file_path = file_path.replace("\\", "/")
            if file_path.startswith("./"):
                file_path = file_path[2:]

            with self.driver.session() as session:
                result = session.run(
                    """
                    MATCH (f:File {path: $path})-[:CONTAINS]->(s:Symbol)
                    OPTIONAL MATCH (s)-[:CALLS]->(called:Symbol)
                    RETURN s.qualified_name as id, s.name as name, s.type as type, 
                           s.line as line, s.signature as signature, s.docstring as docstring,
                           collect(distinct called.qualified_name) as called_symbols
                    ORDER BY s.line
                """,
                    {"path": file_path},
                )

                symbols = []
                for record in result:
                    symbols.append(
                        {
                            "id": record["id"],
                            "name": record["name"],
                            "type": record["type"],
                            "line": record["line"],
                            "signature": record["signature"],
                            "docstring": record["docstring"],
                            "called_symbols": record["called_symbols"],
                        }
                    )

                return symbols

        except Exception as e:
            logger.error(f"Error getting file symbols for {file_path}: {e}")
            return []

    def search_symbols(
        self, query: str, symbol_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
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
                    result = session.run(
                        """
                        MATCH (s:Symbol)
                        WHERE s.type = $type AND (s.name CONTAINS $query OR s.signature CONTAINS $query OR s.docstring CONTAINS $query)
                        RETURN s.qualified_name as id, s.name as name, s.type as type, 
                               s.line as line, s.signature as signature, s.docstring as docstring
                        LIMIT 50
                    """,
                        {"query": query, "type": symbol_type},
                    )
                else:
                    result = session.run(
                        """
                        MATCH (s:Symbol)
                        WHERE s.name CONTAINS $query OR s.signature CONTAINS $query OR s.docstring CONTAINS $query
                        RETURN s.qualified_name as id, s.name as name, s.type as type, 
                               s.line as line, s.signature as signature, s.docstring as docstring
                        LIMIT 50
                    """,
                        {"query": query},
                    )

                symbols = []
                for record in result:
                    symbols.append(
                        {
                            "id": record["id"],
                            "name": record["name"],
                            "type": record["type"],
                            "line": record["line"],
                            "signature": record["signature"],
                            "docstring": record["docstring"],
                        }
                    )

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
                result = session.run(
                    """
                    MATCH (caller:Symbol)-[:CALLS]->(called:Symbol {qualified_name: $symbol_name})
                    RETURN caller.qualified_name as caller_id
                """,
                    {"symbol_name": symbol_name},
                )

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
                called_result = session.run(
                    """
                    MATCH (caller:Symbol {qualified_name: $symbol_name})-[:CALLS]->(called:Symbol)
                    RETURN called.qualified_name as called_id
                """,
                    {"symbol_name": symbol_name},
                )

                called = [record["called_id"] for record in called_result]

                # Get symbols that call this symbol
                caller_result = session.run(
                    """
                    MATCH (caller:Symbol)-[:CALLS]->(called:Symbol {qualified_name: $symbol_name})
                    RETURN caller.qualified_name as caller_id
                """,
                    {"symbol_name": symbol_name},
                )

                callers = [record["caller_id"] for record in caller_result]

                return {"callers": callers, "called": called}

        except Exception as e:
            logger.error(f"Error getting symbol dependencies: {e}")
            return {"callers": [], "called": []}

    def _compute_features(self, dimensions=20):
        """Compute numerical features nodes in the graph."""
        logger.info("Computing features for clustering...")

        with self.driver.session() as session:
            # Count outgoing calls for each function
            session.run("""
                MATCH (f)-[:CALLS]->(other)
                WHERE f <> other
                WITH f, count(other) as outgoing_calls
                SET f.outgoing_calls = outgoing_calls
            """)

            # Count incoming calls for each function
            session.run("""
                MATCH (f)<-[:CALLS]-(other)
                WHERE f <> other
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

            # Count arguments and docstring size for each function
            session.run("""
                MATCH (f)
                SET f.arg_count = CASE true
                  WHEN f.signature IS NULL THEN 0
                  WHEN f.type = "file" THEN 0
                  WHEN f.signature CONTAINS "():" THEN 0
                  WHEN f.signature CONTAINS "," THEN size(split(f.signature, ","))
                  ELSE 1
                END,
                f.docstring_size = CASE f.docstring
                    WHEN NULL THEN 0
                    ELSE SIZE(f.docstring)
                END
            """)

            # # Add file properties to functions
            # session.run("""
            #     MATCH (file:File)-[:CONTAINS]->(f:Function)
            #     SET f.file_line_count = CASE WHEN file.line_count IS NOT NULL THEN file.line_count ELSE 0 END,
            #         f.file_import_count = CASE WHEN file.imports IS NOT NULL THEN size(file.imports) ELSE 0 END
            # """)

            # Check if graph projection exists and drop it if it does
            result = session.run(
                "CALL gds.graph.exists('code-functions') YIELD exists"
            )
            if result.single()["exists"]:
                session.run("CALL gds.graph.drop('code-functions')")

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
            session.run(f"""
                CALL gds.fastRP.write('code-functions',
                {{
                    embeddingDimension: {dimensions},
                    writeProperty: 'embedding'
                    }}
                )
            """
            )
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

    def _run_kmeans_clustering(self, k=5, max_iterations=50, random_seed=42):
        """
        Run K-means clustering on Function nodes using computed features.

        Args:
            k: Number of clusters (default: 5)
            max_iterations: Maximum number of iterations (default: 50)
            random_seed: Random seed for reproducibility (default: 42)
        """
        if not max_iterations:
            max_iterations = 50
        logger.info(f"Running K-means clustering with k={k} for {max_iterations=}...")

        try:
            with self.driver.session() as session:
                # Check if GDS library is installed
                try:
                    session.run("CALL gds.list()")
                except Exception as e:
                    logger.error(
                        f"Neo4j Graph Data Science library not installed or not accessible: {e}"
                    )
                    return False

                # Check if graph projection exists and drop it if it does
                result = session.run(
                    "CALL gds.graph.exists('code-functions') YIELD exists"
                )
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
                    logger.info(
                        f"K-means clustering completed: {record['nodePropertiesWritten']} nodes written in {record['computeMillis']}ms"
                    )

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

                    #  avg(f.file_line_count) as avg_lines,
                    #  avg(f.file_import_count) as avg_imports,
            # Compute cluster statistics
            result = session.run("""
                MATCH (f:Function)
                WHERE f.cluster IS NOT NULL
                WITH f.cluster as cluster,
                    avg(f.outgoing_calls) as avg_outgoing,
                    avg(f.incoming_calls) as avg_incoming,
                    avg(f.arg_count) as avg_args,
                    avg(f.docstring_size) as avg_docstring_size,
                    count(*) as count
                MERGE (c:Cluster {id: cluster})
                SET c.count = count,
                    c.avg_outgoing_calls = avg_outgoing,
                    c.avg_incoming_calls = avg_incoming,
                    c.avg_args = avg_args,
                    c.docstring_size = avg_docstring_size
                WITH c as c
                MATCH (stats:ClusterStatistics {id: 'cluster_stats'})
                MERGE (stats)-[:HAS_CLUSTER]->(c)
                RETURN c.id, c.count
            """)

            clusters = [
                f"Cluster {record['c.id']}: {record['c.count']} functions"
                for record in result
            ]

            logger.info(f"Computed statistics for {len(clusters)} clusters")
            result = session.run("""
                MATCH (f:Symbol)
                WHERE f.cluster IS NOT NULL
                WITH f as f,
                     f.cluster as cluster
                SET f:$(toString(f.cluster))
                WITH f,
                    f.cluster as cluster
                MERGE (c:Cluster {id: cluster})
                MERGE (f)-[:HAS_CLUSTER]->(c)
                RETURN f.id, f.cluster 
            """)
            logger.info(f"Clusters: {', '.join(clusters)}")

    def close(self):
        """Close the Neo4j driver."""
        if self.driver:
            self.driver.close()
            logger.info("Closed Neo4j driver")
