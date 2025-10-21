# Neo4j Index for Code-Index-MCP

This document describes the Neo4j-based code indexing system for the Code-Index-MCP project.

## Overview

The Neo4j index provides a graph-based representation of your codebase, allowing for powerful queries and visualizations of code relationships. It uses the Neo4j graph database to store information about files, symbols, and their relationships.

## Features

- **Graph-based code representation**: Code is represented as a graph with nodes for files and symbols, and relationships between them.
- **Advanced relationship queries**: Easily query relationships between code elements, such as "find all callers of this function" or "find all classes that implement this interface".
- **Powerful query language**: Use the Cypher query language to perform complex queries on your codebase.
- **Visualization capabilities**: Visualize your code structure using Neo4j's built-in visualization tools.

## Requirements

- Neo4j database (local or remote)
- Neo4j Python driver (`neo4j>=5.8.0`)

## Setup

1. Install Neo4j:
   - Download and install Neo4j from [neo4j.com](https://neo4j.com/download/)
   - Or use Docker: `docker run -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j:latest`

2. Install the Neo4j Python driver:
   ```bash
   pip install neo4j>=5.8.0
   ```

3. Configure Neo4j connection:
   - Set environment variables:
     ```bash
     export NEO4J_URI="bolt://localhost:7687"
     export NEO4J_USER="neo4j"
     export NEO4J_PASSWORD="password"
     export NEO4J_DATABASE="neo4j"
     ```
   - Or provide configuration when using the API (see below)

4. Set the index type to Neo4j:
   ```bash
   export CODE_INDEX_TYPE="neo4j"
   ```

## Usage

### Using the Neo4j Index Manager Directly

```python
from code_index_mcp.indexing.neo4j_index_manager import get_neo4j_index_manager

# Get Neo4j index manager
neo4j_manager = get_neo4j_index_manager()

# Set Neo4j configuration (optional, will use environment variables if not set)
neo4j_manager.set_neo4j_config(
    uri="bolt://localhost:7687",
    user="neo4j",
    password="password",
    database="neo4j"
)

# Set project path
neo4j_manager.set_project_path("/path/to/your/project")

# Initialize Neo4j manager
neo4j_manager.initialize()

# Build index
neo4j_manager.refresh_index()

# Get index provider
provider = neo4j_manager.get_provider()

# Get file list
files = provider.get_file_list()

# Get symbols for a file
symbols = provider.query_symbols("src/main.py")

# Search files
matching_files = provider.search_files("*.py")

# Get index metadata
metadata = provider.get_metadata()
```

### Using the Index Factory

```python
from code_index_mcp.indexing.index_factory import get_index_manager, NEO4J_INDEX_TYPE

# Get Neo4j index manager from factory
manager = get_index_manager(NEO4J_INDEX_TYPE)

# Set project path
manager.set_project_path("/path/to/your/project")

# Initialize manager
manager.initialize()

# Build index
manager.refresh_index()

# Get index provider
provider = manager.get_provider()

# Use provider as above
```

### Migrating from JSON to Neo4j

```python
from code_index_mcp.indexing.index_migration import IndexMigrationTool

# Migrate from JSON to Neo4j
success = IndexMigrationTool.migrate_json_to_neo4j(
    project_path="/path/to/your/project",
    neo4j_uri="bolt://localhost:7687",
    neo4j_user="neo4j",
    neo4j_password="password",
    neo4j_database="neo4j"
)

# Verify migration
verification = IndexMigrationTool.verify_migration("/path/to/your/project")
print(verification)
```

### Command-line Testing

```bash
# Test Neo4j index
python -m code_index_mcp.indexing.test_neo4j_index --project-path /path/to/your/project

# Migrate from JSON to Neo4j
python -m code_index_mcp.indexing.test_neo4j_index --project-path /path/to/your/project --migrate

# Run clustering and analyze cross-file calls
python -m code_index_mcp.indexing.neo4j_cli --project-path /path/to/project --neo4j-uri bolt://localhost:7687 --neo4j-user neo4j --neo4j-password password --refresh --clustering --k 5 --show-clusters --show-cross-file-calls

# Test the implementation
python -m code_index_mcp.indexing.test_neo4j_clustering --project-path /path/to/project --neo4j-uri bolt://localhost:7687 --neo4j-user neo4j --neo4j-password password --k 5
uv run run_test_neo4j_clustering.py --neo4j-password "2VZi3xnzpl&2ZThU" --project-path "/Users/conor.fehilly/Documents/repos/dst-python-seomax-redesign" --k 5


```

## Neo4j Schema

The Neo4j index uses the following schema:

### Nodes

- **File**: Represents a source code file
  - Properties:
    - `path`: Relative file path
    - `language`: Programming language
    - `line_count`: Number of lines
    - `imports`: List of imported modules
    - `exports`: List of exported symbols

- **Symbol**: Represents a code symbol (function, class, method, etc.)
  - Properties:
    - `qualified_name`: Fully qualified name
    - `name`: Symbol name
    - `type`: Symbol type (function, class, method, etc.)
    - `line`: Line number
    - `signature`: Function/method signature
    - `docstring`: Documentation string

- **IndexMetadata**: Stores metadata about the index
  - Properties:
    - `project_path`: Project path
    - `indexed_files`: Number of indexed files
    - `index_version`: Index version
    - `timestamp`: Creation timestamp
    - `languages`: List of languages
    - `total_symbols`: Total number of symbols

### Relationships

- **CONTAINS**: File contains Symbol
- **CALLS**: Symbol calls Symbol
- **EXTENDS**: Symbol extends Symbol (for class inheritance)
- **IMPLEMENTS**: Symbol implements Symbol (for interfaces)
- **IMPORTS**: File imports Symbol

## Advanced Queries

You can use Cypher queries to perform advanced queries on your codebase. Here are some examples:

### Find all callers of a function

```cypher
MATCH (caller:Symbol)-[:CALLS]->(called:Symbol {name: "process_data"})
RETURN caller.name, caller.file, caller.line
```

### Find all classes that extend a base class

```cypher
MATCH (derived:Symbol:Class)-[:EXTENDS]->(base:Symbol:Class {name: "BaseClass"})
RETURN derived.name, derived.file, derived.line
```

### Find files with the most symbols

```cypher
MATCH (f:File)-[:CONTAINS]->(s:Symbol)
RETURN f.path, count(s) as symbol_count
ORDER BY symbol_count DESC
LIMIT 10
```

### Find the most called functions

```cypher
MATCH (caller:Symbol)-[:CALLS]->(called:Symbol)
RETURN called.name, count(caller) as caller_count
ORDER BY caller_count DESC
LIMIT 10
```

## Performance Considerations

- Neo4j is optimized for relationship queries, but may be slower than JSON for simple file listing.
- For large codebases, consider using Neo4j Enterprise Edition for better performance.
- Use appropriate indexes for your most common queries.
- Consider using a dedicated Neo4j server for production use.

## Troubleshooting

- **Connection issues**: Ensure Neo4j is running and accessible at the configured URI.
- **Authentication issues**: Check your Neo4j username and password.
- **Performance issues**: Ensure you have enough memory allocated to Neo4j.
- **Index building issues**: Check the logs for errors during index building.
