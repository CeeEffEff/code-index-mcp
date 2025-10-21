# Neo4j MCP Tools Specifications for Code Analysis

This document provides detailed specifications for MCP tools that wrap Neo4j queries for code analysis. These tools encapsulate common code analysis patterns, provide user-friendly interfaces to complex Neo4j queries, and have sensible limits on data returned.

## Data Model Overview

The Neo4j database used by these tools has the following schema:

### Nodes

- **File**: Represents a source code file
  - Properties: `path`, `language`, `line_count`, `imports`, `exports`
- **Symbol**: Represents a code symbol (function, class, method, etc.)
  - Properties: `qualified_name`, `name`, `type`, `line`, `signature`, `docstring`
  - Labels: Can have additional labels like `:Function`, `:Class` based on type
- **Cluster**: Represents a cluster of similar functions from K-means clustering
  - Properties: `id`, `count`, `avg_outgoing_calls`, `avg_incoming_calls`, `avg_args`, etc.

### Relationships

- **CONTAINS**: File contains Symbol
- **CALLS**: Symbol calls Symbol
- **EXTENDS**: Symbol extends Symbol (for class inheritance)
- **IMPLEMENTS**: Symbol implements Symbol (for interfaces)

## MCP Tool Specifications

### 1. Function Complexity Analyzer

**Purpose**: Find functions with high complexity based on various metrics

**Parameters**:

- `language` (optional): Filter by programming language (e.g., "python", "javascript")
- `metric` (required): Type of complexity to analyze ("parameters", "length", "nesting", "cyclomatic", "calls")
- `limit` (optional): Maximum number of results to return (default: 20)
- `minThreshold` (optional): Minimum threshold for the metric (e.g., min number of parameters)

**Returns**: List of functions with their complexity metrics, file paths, and relevant metadata

**Implementation**:

```python
def function_complexity_analyzer(language=None, metric="parameters", limit=20, minThreshold=None):
    """
    Find functions with high complexity based on various metrics.
    
    Args:
        language: Filter by programming language (e.g., "python", "javascript")
        metric: Type of complexity to analyze ("parameters", "length", "nesting", "cyclomatic", "calls")
        limit: Maximum number of results to return (default: 20)
        minThreshold: Minimum threshold for the metric (e.g., min number of parameters)
        
    Returns:
        List of functions with their complexity metrics, file paths, and relevant metadata
    """
    with driver.session() as session:
        # Base query
        query = """
            MATCH (file:File)-[:CONTAINS]->(func:Function)
            WHERE 1=1
        """
        
        # Add language filter if provided
        if language:
            query += f" AND file.language = '{language}'"
        
        # Add metric-specific conditions and sorting
        if metric == "parameters":
            query += """
                AND func.arg_count IS NOT NULL
                WITH func, file, func.arg_count as complexity
            """
            if minThreshold:
                query += f" WHERE complexity >= {minThreshold}"
            query += " ORDER BY complexity DESC"
        
        elif metric == "length":
            query += """
                WITH func, file, size(split(func.signature, ';')) as complexity
            """
            if minThreshold:
                query += f" WHERE complexity >= {minThreshold}"
            query += " ORDER BY complexity DESC"
        
        elif metric == "calls":
            query += """
                MATCH (func)-[:CALLS]->(called)
                WITH func, file, count(called) as complexity
            """
            if minThreshold:
                query += f" WHERE complexity >= {minThreshold}"
            query += " ORDER BY complexity DESC"
        
        elif metric == "cyclomatic":
            # Approximation of cyclomatic complexity based on conditional keywords in signature
            query += """
                WITH func, file, 
                     1 + 
                     size(apoc.text.regexGroups(func.signature, '\\bif\\b|\\belse\\b|\\bfor\\b|\\bwhile\\b|\\bcatch\\b|\\bcase\\b|\\b\\?\\b|\\b&&\\b|\\b\\|\\|\\b')) as complexity
            """
            if minThreshold:
                query += f" WHERE complexity >= {minThreshold}"
            query += " ORDER BY complexity DESC"
        
        # Finalize query with return statement and limit
        query += f"""
            RETURN func.name as name, 
                   func.qualified_name as qualified_name,
                   file.path as file_path,
                   file.language as language,
                   func.signature as signature,
                   complexity
            LIMIT {limit}
        """
        
        result = session.run(query)
        return [dict(record) for record in result]
```

**Example Cypher Query**:

```cypher
MATCH (file:File)-[:CONTAINS]->(func:Function)
WHERE file.language = 'python'
MATCH (func)-[:CALLS]->(called)
WITH func, file, count(called) as complexity
WHERE complexity >= 5
RETURN func.name as name, 
       func.qualified_name as qualified_name,
       file.path as file_path,
       file.language as language,
       func.signature as signature,
       complexity
ORDER BY complexity DESC
LIMIT 20
```

### 2. File Size Analyzer

**Purpose**: Identify large files in the codebase

**Parameters**:

- `language` (optional): Filter by programming language
- `metric` (required): Measure to use ("lines", "symbols", "functions", "classes")
- `limit` (optional): Maximum number of results to return (default: 20)
- `sortOrder` (optional): Sort direction ("desc" or "asc", default: "desc")

**Returns**: List of files with their size metrics and paths

**Implementation**:

```python
def file_size_analyzer(language=None, metric="lines", limit=20, sortOrder="desc"):
    """
    Identify large files in the codebase.
    
    Args:
        language: Filter by programming language
        metric: Measure to use ("lines", "symbols", "functions", "classes")
        limit: Maximum number of results to return (default: 20)
        sortOrder: Sort direction ("desc" or "asc")
        
    Returns:
        List of files with their size metrics and paths
    """
    with driver.session() as session:
        # Base query
        query = """
            MATCH (file:File)
            WHERE 1=1
        """
        
        # Add language filter if provided
        if language:
            query += f" AND file.language = '{language}'"
        
        # Add metric-specific conditions and sorting
        if metric == "lines":
            query += """
                WITH file, file.line_count as size
                ORDER BY size
            """
        
        elif metric == "symbols":
            query += """
                MATCH (file)-[:CONTAINS]->(symbol)
                WITH file, count(symbol) as size
                ORDER BY size
            """
        
        elif metric == "functions":
            query += """
                MATCH (file)-[:CONTAINS]->(func:Function)
                WITH file, count(func) as size
                ORDER BY size
            """
        
        elif metric == "classes":
            query += """
                MATCH (file)-[:CONTAINS]->(class:Class)
                WITH file, count(class) as size
                ORDER BY size
            """
        
        # Add sort order
        if sortOrder.lower() == "desc":
            query += " DESC"
        else:
            query += " ASC"
        
        # Finalize query with return statement and limit
        query += f"""
            RETURN file.path as path,
                   file.language as language,
                   size,
                   file.line_count as line_count
            LIMIT {limit}
        """
        
        result = session.run(query)
        return [dict(record) for record in result]
```

**Example Cypher Query**:

```cypher
MATCH (file:File)
WHERE file.language = 'javascript'
MATCH (file)-[:CONTAINS]->(func:Function)
WITH file, count(func) as size
ORDER BY size DESC
RETURN file.path as path,
       file.language as language,
       size,
       file.line_count as line_count
LIMIT 20
```

### 3. Code Structure Visualizer

**Purpose**: Generate graph visualizations of code structure

**Parameters**:

- `scope` (required): Level of analysis ("file", "module", "package", "project")
- `focusEntity` (required): Entity to focus on (file path, module name, etc.)
- `relationshipTypes` (optional): Types of relationships to include ("imports", "calls", "inherits", "all")
- `depth` (optional): How many levels of relationships to traverse (default: 2)
- `limit` (optional): Maximum number of nodes to include (default: 50)

**Returns**: Graph data structure suitable for visualization

**Implementation**:

```python
def code_structure_visualizer(scope, focusEntity, relationshipTypes="all", depth=2, limit=50):
    """
    Generate graph visualizations of code structure.
    
    Args:
        scope: Level of analysis ("file", "module", "package", "project")
        focusEntity: Entity to focus on (file path, module name, etc.)
        relationshipTypes: Types of relationships to include ("imports", "calls", "inherits", "all")
        depth: How many levels of relationships to traverse (default: 2)
        limit: Maximum number of nodes to include (default: 50)
        
    Returns:
        Graph data structure suitable for visualization
    """
    with driver.session() as session:
        # Determine the starting node based on scope and focusEntity
        if scope == "file":
            start_node_query = f"MATCH (n:File) WHERE n.path = '{focusEntity}'"
        elif scope == "module":
            start_node_query = f"MATCH (n:File) WHERE n.path STARTS WITH '{focusEntity}/'"
        elif scope == "package":
            start_node_query = f"MATCH (n:File) WHERE n.path CONTAINS '/{focusEntity}/'"
        elif scope == "project":
            start_node_query = f"MATCH (n:File) WHERE n.path STARTS WITH '{focusEntity}'"
        
        # Determine relationship types to include
        if relationshipTypes == "imports":
            rel_types = ["IMPORTS"]
        elif relationshipTypes == "calls":
            rel_types = ["CALLS"]
        elif relationshipTypes == "inherits":
            rel_types = ["EXTENDS", "IMPLEMENTS"]
        else:  # "all"
            rel_types = ["CONTAINS", "CALLS", "EXTENDS", "IMPLEMENTS", "IMPORTS"]
        
        rel_pattern = "|".join([f":{rel}" for rel in rel_types])
        
        # Build the query
        query = f"""
            {start_node_query}
            CALL apoc.path.expand(n, "{rel_pattern}", "", 1, {depth}) YIELD path
            WITH path, relationships(path) as rels
            LIMIT {limit}
            RETURN 
                [n IN nodes(path) | {{
                    id: id(n),
                    labels: labels(n),
                    properties: properties(n)
                }}] as nodes,
                [r IN rels | {{
                    id: id(r),
                    type: type(r),
                    source: id(startNode(r)),
                    target: id(endNode(r)),
                    properties: properties(r)
                }}] as relationships
        """
        
        result = session.run(query)
        record = result.single()
        
        if not record:
            return {"nodes": [], "relationships": []}
        
        # Process the result into a graph structure
        nodes = record["nodes"]
        relationships = record["relationships"]
        
        # Deduplicate nodes and relationships
        unique_nodes = {}
        for node in nodes:
            if node["id"] not in unique_nodes:
                unique_nodes[node["id"]] = node
        
        unique_rels = {}
        for rel in relationships:
            if rel["id"] not in unique_rels:
                unique_rels[rel["id"]] = rel
        
        return {
            "nodes": list(unique_nodes.values()),
            "relationships": list(unique_rels.values())
        }
```

**Example Cypher Query**:

```cypher
MATCH (n:File) WHERE n.path = 'src/main.py'
CALL apoc.path.expand(n, ":CONTAINS|:CALLS", "", 1, 2) YIELD path
WITH path, relationships(path) as rels
LIMIT 50
RETURN 
    [n IN nodes(path) | {
        id: id(n),
        labels: labels(n),
        properties: properties(n)
    }] as nodes,
    [r IN rels | {
        id: id(r),
        type: type(r),
        source: id(startNode(r)),
        target: id(endNode(r)),
        properties: properties(r)
    }] as relationships
```

### 4. Dependency Analyzer

**Purpose**: Analyze dependencies between code entities

**Parameters**:

- `entityType` (required): Type of entity to analyze ("file", "function", "class", "module")
- `entityName` (required): Name of the specific entity to analyze
- `direction` (optional): Direction of dependencies ("incoming", "outgoing", "both", default: "both")
- `limit` (optional): Maximum number of results to return (default: 30)

**Returns**: List of dependencies with their relationship types and strengths

**Implementation**:

```python
def dependency_analyzer(entityType, entityName, direction="both", limit=30):
    """
    Analyze dependencies between code entities.
    
    Args:
        entityType: Type of entity to analyze ("file", "function", "class", "module")
        entityName: Name of the specific entity to analyze
        direction: Direction of dependencies ("incoming", "outgoing", "both")
        limit: Maximum number of results to return (default: 30)
        
    Returns:
        List of dependencies with their relationship types and strengths
    """
    with driver.session() as session:
        # Determine the starting node based on entityType and entityName
        if entityType == "file":
            start_node_query = f"MATCH (n:File) WHERE n.path = '{entityName}'"
        elif entityType == "function":
            start_node_query = f"MATCH (n:Function) WHERE n.name = '{entityName}' OR n.qualified_name = '{entityName}'"
        elif entityType == "class":
            start_node_query = f"MATCH (n:Class) WHERE n.name = '{entityName}' OR n.qualified_name = '{entityName}'"
        elif entityType == "module":
            # For module, we'll look at all files in the module
            start_node_query = f"MATCH (n:File) WHERE n.path STARTS WITH '{entityName}/'"
        
        # Build queries based on direction
        if direction == "incoming" or direction == "both":
            incoming_query = f"""
                {start_node_query}
                MATCH (other)-[r]->(n)
                WHERE type(r) <> 'CONTAINS'
                WITH other, type(r) as relationship_type, count(r) as strength
                ORDER BY strength DESC
                LIMIT {limit}
                RETURN 'incoming' as direction, 
                       other.name as entity_name, 
                       labels(other) as entity_type,
                       relationship_type,
                       strength
            """
        else:
            incoming_query = ""
        
        if direction == "outgoing" or direction == "both":
            outgoing_query = f"""
                {start_node_query}
                MATCH (n)-[r]->(other)
                WHERE type(r) <> 'CONTAINS'
                WITH other, type(r) as relationship_type, count(r) as strength
                ORDER BY strength DESC
                LIMIT {limit}
                RETURN 'outgoing' as direction, 
                       other.name as entity_name, 
                       labels(other) as entity_type,
                       relationship_type,
                       strength
            """
        else:
            outgoing_query = ""
        
        # Combine queries if needed
        if direction == "both":
            query = f"{incoming_query} UNION {outgoing_query}"
        elif direction == "incoming":
            query = incoming_query
        else:  # "outgoing"
            query = outgoing_query
        
        result = session.run(query)
        return [dict(record) for record in result]
```

**Example Cypher Query**:

```cypher
MATCH (n:Function) WHERE n.name = 'process_data' OR n.qualified_name = 'process_data'
MATCH (other)-[r]->(n)
WHERE type(r) <> 'CONTAINS'
WITH other, type(r) as relationship_type, count(r) as strength
ORDER BY strength DESC
LIMIT 30
RETURN 'incoming' as direction, 
       other.name as entity_name, 
       labels(other) as entity_type,
       relationship_type,
       strength

UNION

MATCH (n:Function) WHERE n.name = 'process_data' OR n.qualified_name = 'process_data'
MATCH (n)-[r]->(other)
WHERE type(r) <> 'CONTAINS'
WITH other, type(r) as relationship_type, count(r) as strength
ORDER BY strength DESC
LIMIT 30
RETURN 'outgoing' as direction, 
       other.name as entity_name, 
       labels(other) as entity_type,
       relationship_type,
       strength
```

### 5. Centrality Metrics Calculator

**Purpose**: Calculate centrality metrics to identify important code entities

**Parameters**:

- `algorithm` (required): Centrality algorithm to use ("pagerank", "betweenness", "closeness", "degree")
- `entityType` (optional): Type of entity to analyze ("file", "function", "class", default: "function")
- `limit` (optional): Maximum number of results to return (default: 20)
- `minValue` (optional): Minimum value threshold for results

**Returns**: List of entities with their centrality scores

**Implementation**:

```python
def centrality_metrics_calculator(algorithm, entityType="function", limit=20, minValue=None):
    """
    Calculate centrality metrics to identify important code entities.
    
    Args:
        algorithm: Centrality algorithm to use ("pagerank", "betweenness", "closeness", "degree")
        entityType: Type of entity to analyze ("file", "function", "class")
        limit: Maximum number of results to return (default: 20)
        minValue: Minimum value threshold for results
        
    Returns:
        List of entities with their centrality scores
    """
    with driver.session() as session:
        # Create graph projection based on entityType
        if entityType == "file":
            node_label = "File"
            relationship_type = "IMPORTS"
        elif entityType == "function":
            node_label = "Function"
            relationship_type = "CALLS"
        elif entityType == "class":
            node_label = "Class"
            relationship_type = "EXTENDS"
        
        # Check if graph projection exists and drop it if it does
        check_query = "CALL gds.graph.exists('centrality-graph') YIELD exists"
        check_result = session.run(check_query)
        if check_result.single()["exists"]:
            session.run("CALL gds.graph.drop('centrality-graph')")
        
        # Create graph projection
        projection_query = f"""
            CALL gds.graph.project(
                'centrality-graph',
                '{node_label}',
                '{relationship_type}',
                {{
                    relationshipProperties: 'weight'
                }}
            )
        """
        session.run(projection_query)
        
        # Run centrality algorithm
        if algorithm == "pagerank":
            algo_query = """
                CALL gds.pageRank.stream('centrality-graph')
                YIELD nodeId, score
                WITH gds.util.asNode(nodeId) as node, score
                ORDER BY score DESC
            """
        elif algorithm == "betweenness":
            algo_query = """
                CALL gds.betweenness.stream('centrality-graph')
                YIELD nodeId, score
                WITH gds.util.asNode(nodeId) as node, score
                ORDER BY score DESC
            """
        elif algorithm == "closeness":
            algo_query = """
                CALL gds.closeness.stream('centrality-graph')
                YIELD nodeId, score
                WITH gds.util.asNode(nodeId) as node, score
                ORDER BY score DESC
            """
        elif algorithm == "degree":
            algo_query = """
                CALL gds.degree.stream('centrality-graph')
                YIELD nodeId, score
                WITH gds.util.asNode(nodeId) as node, score
                ORDER BY score DESC
            """
        
        # Add minimum value filter if provided
        if minValue is not None:
            algo_query += f" WHERE score >= {minValue}"
        
        # Add return statement and limit
        algo_query += f"""
            RETURN node.name as name,
                   node.qualified_name as qualified_name,
                   labels(node) as type,
                   score as centrality_score
            LIMIT {limit}
        """
        
        result = session.run(algo_query)
        centrality_results = [dict(record) for record in result]
        
        # Drop graph projection
        session.run("CALL gds.graph.drop('centrality-graph')")
        
        return centrality_results
```

**Example Cypher Query**:

```cypher
CALL gds.graph.project(
    'centrality-graph',
    'Function',
    'CALLS',
    {
        relationshipProperties: 'weight'
    }
)

CALL gds.pageRank.stream('centrality-graph')
YIELD nodeId, score
WITH gds.util.asNode(nodeId) as node, score
ORDER BY score DESC
WHERE score >= 0.1
RETURN node.name as name,
       node.qualified_name as qualified_name,
       labels(node) as type,
       score as centrality_score
LIMIT 20

CALL gds.graph.drop('centrality-graph')
```

### 6. Code Clustering Tool

**Purpose**: Group similar code entities using graph clustering algorithms

**Parameters**:

- `algorithm` (required): Clustering algorithm to use ("louvain", "label_propagation", "k_means")
- `entityType` (optional): Type of entity to cluster ("file", "function", "class", default: "function")
- `relationshipType` (optional): Type of relationships to consider for clustering (default: "CALLS")
- `minClusterSize` (optional): Minimum size of clusters to return (default: 3)
- `limit` (optional): Maximum number of clusters to return (default: 10)

**Returns**: Clusters of code entities with similarity metrics

**Implementation**:

```python
def code_clustering_tool(algorithm, entityType="function", relationshipType="CALLS", minClusterSize=3, limit=10):
    """
    Group similar code entities using graph clustering algorithms.
    
    Args:
        algorithm: Clustering algorithm to use ("louvain", "label_propagation", "k_means")
        entityType: Type of entity to cluster ("file", "function", "class")
        relationshipType: Type of relationships to consider for clustering
        minClusterSize: Minimum size of clusters to return
        limit: Maximum number of clusters to return (default: 10)
        
    Returns:
        Clusters of code entities with similarity metrics
    """
    with driver.session() as session:
        # Create graph projection based on entityType
        if entityType == "file":
            node_label = "File"
        elif entityType == "function":
            node_label = "Function"
        elif entityType == "class":
            node_label = "Class"
        
        # Check if graph projection exists and drop it if it does
        check_query = "CALL gds.graph.exists('clustering-graph') YIELD exists"
        check_result = session.run(check_query)
        if check_result.single()["exists"]:
            session.run("CALL gds.graph.drop('clustering-graph')")
        
        # Create graph projection
        projection_query = f"""
            CALL gds.graph.project(
                'clustering-graph',
                '{node_label}',
                '{relationshipType}'
            )
        """
        session.run(projection_query)
        
        # Run clustering algorithm
        if algorithm == "louvain":
            algo_query = """
                CALL gds.louvain.stream('clustering-graph')
                YIELD nodeId, communityId
                WITH gds.util.asNode(nodeId) as node, communityId
                RETURN communityId as cluster_id, collect(node) as nodes, count(*) as size
                ORDER BY size DESC
                WHERE size >= $minClusterSize
                LIMIT $limit
            """
        elif algorithm == "label_propagation":
            algo_query = """
                CALL gds.labelPropagation.stream('clustering-graph')
                YIELD nodeId, communityId
                WITH gds.util.asNode(nodeId) as node, communityId
                RETURN communityId as cluster_id, collect(node) as nodes, count(*) as size
                ORDER BY size DESC
                WHERE size >= $minClusterSize
                LIMIT $limit
            """
        elif algorithm == "k_means":
            # For k-means, we need to compute features first
            session.run("""
                MATCH (n:Function)
                OPTIONAL MATCH (n)-[:CALLS]->(other)
                WITH n, count(other) as outgoing_calls
                OPTIONAL MATCH (other)-[:CALLS]->(n)
                WITH n, outgoing_calls, count(other) as incoming_calls
                SET n.embedding = [toFloat(outgoing_calls), toFloat(incoming_calls)]
            """)
            
            # Update graph projection to include embedding property
            session.run("CALL gds.graph.drop('clustering-graph')")
            session.run(f"""
                CALL gds.graph.project(
                    'clustering-graph',
                    '{node_label}',
                    '{relationshipType}',
                    {{
                        nodeProperties: ['embedding']
                    }}
                )
            """)
            
            algo_query = """
                CALL gds.kmeans.stream('clustering-graph', {
                    k: $limit,
                    nodeProperty: 'embedding'
                })
                YIELD nodeId, communityId
                WITH gds.util.asNode(nodeId) as node, communityId
                RETURN communityId as cluster_id, collect(node) as nodes, count(*) as size
                ORDER BY size DESC
                WHERE size >= $minClusterSize
                LIMIT $limit
            """
        
        # Execute clustering query
        result = session.run(algo_query, {"minClusterSize": minClusterSize, "limit": limit})
        
        # Process results
        clusters = []
        for record in result:
            cluster_id = record["cluster_id"]
            nodes = record["nodes"]
            size = record["size"]
            
            # Extract node information
            node_info = []
            for node in nodes:
                node_info.append({
                    "name": node["name"],
                    "qualified_name": node["qualified_name"] if "qualified_name" in node else None,
                    "type": node["type"] if "type" in node else None
                })
            
            clusters.append({
                "cluster_id": cluster_id,
                "size": size,
                "nodes": node_info
            })
        
        # Drop graph projection
        session.run("CALL gds.graph.drop('clustering-graph')")
        
        return clusters
```

**Example Cypher Query**:

```cypher
CALL gds.graph.project(
    'clustering-graph',
    'Function',
    'CALLS'
)

CALL gds.louvain.stream('clustering-graph')
YIELD nodeId, communityId
WITH gds.util.asNode(nodeId) as node, communityId
RETURN communityId as cluster_id, collect(node.name) as node_names, count(*) as size
ORDER BY size DESC
WHERE size >= 3
LIMIT 10

CALL gds.graph.drop('clustering-graph')
```

### 7. Nested Code Detector

**Purpose**: Find deeply nested code structures

**Parameters**:

- `language` (optional): Programming language to analyze
- `minDepth` (optional): Minimum nesting depth to report (default: 4)
- `limit` (optional): Maximum number of results to return (default: 20)
- `includeContext` (optional): Whether to include surrounding code context (default: true)

**Returns**: List of nested code locations with their depths and context

**Implementation**:

```python
def nested_code_detector(language=None, minDepth=4, limit=20, includeContext=True):
    """
    Find deeply nested code structures.
    
    Args:
        language: Programming language to analyze
        minDepth: Minimum nesting depth to report (default: 4)
        limit: Maximum number of results to return (default: 20)
        includeContext: Whether to include surrounding code context (default: true)
        
    Returns:
        List of nested code locations with their depths and context
    """
    with driver.session() as session:
        # Base query
        query = """
            MATCH (file:File)-[:CONTAINS]->(func:Function)
            WHERE func.signature IS NOT NULL
        """
        
        # Add language filter if provided
        if language:
            query += f" AND file.language = '{language}'"
        
        # Calculate nesting depth based on indentation patterns in signature
        # This is an approximation and may need to be adjusted based on language
        query += f"""
            WITH file, func,
                 size(apoc.text.regexGroups(func.signature, '(\\{{|\\[|\\(|if|for|while|switch|try|catch)')) as nesting_depth
            WHERE nesting_depth >= {minDepth}
            RETURN func.name as function_name,
                   func.qualified_name as qualified_name,
                   file.path as file_path,
                   file.language as language,
                   func.line as line_number,
                   nesting_depth
            ORDER BY nesting_depth DESC
            LIMIT {limit}
        """
        
        result = session.run(query)
        nested_code = [dict(record) for record in result]
        
        # If includeContext is true, add code context
        if includeContext and nested_code:
            # This would require additional processing to extract code context
            # from the actual source files, which is beyond the scope of this example
            pass
        
        return nested_code
```

**Example Cypher Query**:

```cypher
MATCH (file:File)-[:CONTAINS]->(func:Function)
WHERE func.signature IS NOT NULL AND file.language = 'python'
WITH file, func,
     size(apoc.text.regexGroups(func.signature, '(\\{|\\[|\\(|if|for|while|try|except)')) as nesting_depth
WHERE nesting_depth >= 4
RETURN func.name as function_name,
       func.qualified_name as qualified_name,
       file.path as file_path,
       file.language as language,
       func.line as line_number,
       nesting_depth
ORDER BY nesting_depth DESC
LIMIT 20
```

### 8. Control Flow Complexity Analyzer

**Purpose**: Identify complex control flow patterns

**Parameters**:

- `pattern` (required): Type of pattern to look for ("nested_conditionals", "long_switch", "complex_loops")
- `language` (optional): Programming language to analyze
- `limit` (optional): Maximum number of results to return (default: 15)
- `includeContext` (optional): Whether to include surrounding code context

**Returns**: List of complex control flow instances with their locations and context

**Implementation**:

```python
def control_flow_complexity_analyzer(pattern, language=None, limit=15, includeContext=False):
    """
    Identify complex
