# Useful Neo4j Cypher Queries for Code Repository Analysis

This document contains useful Cypher queries for exploring and analyzing a code repository graph in Neo4j. These queries were used to understand the structure of the graph and extract insights about the codebase.

## Basic Graph Structure Queries

### Count Nodes by Label

```cypher
MATCH (n) 
RETURN labels(n) as node_type, count(n) as count 
ORDER BY count DESC
```

**Insight**: Revealed the distribution of node types in the graph (Files, Functions, Classes, Symbols, etc.)

### View Relationship Types

```cypher
CALL db.relationshipTypes() 
YIELD relationshipType 
RETURN relationshipType 
ORDER BY relationshipType
```

**Insight**: Showed that the graph has two main relationship types: CALLS and CONTAINS

### Count Relationships by Type

```cypher
MATCH ()-[r]->() 
RETURN type(r) as relationship_type, count(r) as count 
ORDER BY count DESC
```

**Insight**: Provided the distribution of relationship types, showing how many CALLS vs CONTAINS relationships exist

## Function Analysis Queries

### Top Functions by Outgoing Calls

```cypher
MATCH (f:Function)-[:CALLS]->(other:Function) 
RETURN f.name, count(other) as outgoing_calls 
ORDER BY outgoing_calls DESC 
LIMIT 5
```

**Insight**: Identified functions that call many other functions, which are likely complex orchestrators or controllers

### Top Functions by Incoming Calls

```cypher
MATCH (f:Function)<-[:CALLS]-(other:Function) 
RETURN f.name, count(other) as incoming_calls 
ORDER BY incoming_calls DESC 
LIMIT 5
```

**Insight**: Found the most frequently called functions, which are likely core utilities or important services

### Function Call Patterns

```cypher
MATCH (caller:Function)-[:CALLS]->(callee:Function) 
MATCH (caller_file:File)-[:CONTAINS]->(caller) 
MATCH (callee_file:File)-[:CONTAINS]->(callee) 
RETURN caller.name, callee.name, caller_file.path, callee_file.path, 
       caller_file.path = callee_file.path as same_file 
LIMIT 5
```

**Insight**: Examined whether functions call other functions in the same file or different files

### Function Signature Analysis

```cypher
MATCH (f:Function) 
RETURN f.name, f.signature 
LIMIT 10
```

**Insight**: Allowed examination of function signatures to understand parameter patterns

## File Analysis Queries

### File Properties

```cypher
MATCH (file:File)-[:CONTAINS]->(f:Function) 
RETURN file, f.name 
LIMIT 1
```

**Insight**: Revealed file properties including path, line count, imports, and language

### Files by Module

```cypher
MATCH (file:File)-[:CONTAINS]->(f:Function) 
WHERE file.path STARTS WITH 'src/' 
RETURN DISTINCT split(file.path, '/')[1] as module 
ORDER BY module
```

**Insight**: Identified the different modules in the src/ directory, showing the high-level structure of the codebase

### Files by Language

```cypher
MATCH (file:File) 
RETURN file.language, count(file) as count 
ORDER BY count DESC
```

**Insight**: Showed the distribution of programming languages in the codebase

## Symbol Analysis Queries

### Symbol Distribution

```cypher
MATCH (s:Symbol) 
RETURN s.type, count(s) as count 
ORDER BY count DESC
```

**Insight**: Provided the distribution of symbol types (functions, classes, variables, etc.)

### Symbol Relationships

```cypher
MATCH (s:Symbol)-[r]-() 
RETURN type(r) as relationship_type, count(r) as count 
LIMIT 5
```

**Insight**: Showed how symbols are connected to other nodes in the graph

## Advanced Analysis Queries

### Cross-Module Function Calls

```cypher
MATCH (caller:Function)-[:CALLS]->(callee:Function) 
MATCH (caller_file:File)-[:CONTAINS]->(caller) 
MATCH (callee_file:File)-[:CONTAINS]->(callee) 
WHERE split(caller_file.path, '/')[1] <> split(callee_file.path, '/')[1] 
RETURN callee.name, count(caller) as cross_module_calls 
ORDER BY cross_module_calls DESC 
LIMIT 5
```

**Insight**: Attempted to find functions that are called from multiple modules (though none were found in this graph)

### Function Complexity Metrics

```cypher
MATCH (f1:Function)-[:CALLS]->(f2:Function) 
WITH f1, count(f2) as outgoing_calls 
MATCH (f1)<-[:CALLS]-(f3:Function) 
WITH f1, outgoing_calls, count(f3) as incoming_calls 
RETURN f1.name, outgoing_calls, incoming_calls, 
       outgoing_calls + incoming_calls as total_connections 
ORDER BY total_connections DESC 
LIMIT 5
```

**Insight**: Combined outgoing and incoming calls to create a "total connections" metric as a proxy for function importance

## Preparing for K-Means Clustering

### Create Numerical Features

```cypher
// Count outgoing calls for each function
MATCH (f:Function)-[:CALLS]->(other:Function)
WITH f, count(other) as outgoing_calls
SET f.outgoing_calls = outgoing_calls;

// Count incoming calls for each function
MATCH (f:Function)<-[:CALLS]-(other:Function)
WITH f, count(other) as incoming_calls
SET f.incoming_calls = incoming_calls;

// Set default values of 0 for functions with no calls
MATCH (f:Function)
WHERE f.outgoing_calls IS NULL
SET f.outgoing_calls = 0;

MATCH (f:Function)
WHERE f.incoming_calls IS NULL
SET f.incoming_calls = 0;
```

**Insight**: Created numerical properties that can be used for clustering algorithms

### Count Arguments for Functions

```cypher
// Count arguments for each function
MATCH (f:Function)
WHERE f.signature IS NOT NULL
SET f.arg_count = CASE true
  WHEN f.type = "file" THEN 0
  WHEN f.signature CONTAINS "():" THEN 0
  WHEN f.signature CONTAINS "," THEN size(split(f.signature, ","))
  ELSE 1
END;
```

**Insight**: Extracted the number of arguments from function signatures to use as a feature for clustering

### Add File Properties to Functions

```cypher
// Add file properties to functions
MATCH (file:File)-[:CONTAINS]->(f:Function)
SET f.file_line_count = CASE WHEN file.line_count IS NOT NULL THEN file.line_count ELSE 0 END,
    f.file_import_count = CASE WHEN file.imports IS NOT NULL THEN size(file.imports) ELSE 0 END;
```

**Insight**: Associated file-level metrics with functions to capture context about the module complexity

### Create Embedding Vector

```cypher
// Create embedding vector for clustering
MATCH (f:Function)
SET f.embedding = [
  toFloat(f.outgoing_calls), 
  toFloat(f.incoming_calls), 
  toFloat(f.arg_count),
  toFloat(f.file_line_count),
  toFloat(f.file_import_count)
];
```

**Insight**: Combined all features into a single vector property for use with k-means clustering

## Analyzing Clustering Results

### View Cluster Distribution

```cypher
// View cluster distribution
MATCH (f:Function)
RETURN f.cluster as cluster, count(*) as count
ORDER BY count DESC;
```

**Insight**: Showed the distribution of functions across clusters, revealing that Cluster 2 (complex processing functions) was the largest with 888 functions (27.3%)

### View Representative Functions by Cluster

```cypher
// View representative functions from each cluster
MATCH (f:Function)
RETURN f.cluster as cluster, f.name as function_name, 
       f.outgoing_calls, f.incoming_calls, f.arg_count,
       f.file_line_count, f.file_import_count
ORDER BY cluster, f.incoming_calls + f.outgoing_calls DESC
LIMIT 25;
```

**Insight**: Identified characteristic functions for each cluster, helping to understand the types of functions in each group

### Analyze Cluster Characteristics

```cypher
// Analyze cluster characteristics
MATCH (f:Function)
WITH f.cluster as cluster,
     avg(f.outgoing_calls) as avg_outgoing,
     avg(f.incoming_calls) as avg_incoming,
     avg(f.arg_count) as avg_args,
     avg(f.file_line_count) as avg_lines,
     avg(f.file_import_count) as avg_imports,
     count(*) as count
RETURN cluster, count, avg_outgoing, avg_incoming, avg_args, avg_lines, avg_imports
ORDER BY cluster;
```

**Insight**: Revealed a clear gradient of complexity across clusters, from simple utility functions (Cluster 0) to complex framework functions (Cluster 4)

### Silhouette Analysis

```cypher
// Calculate silhouette scores for clusters
CALL gds.kmeans.stream('code-functions', {
  nodeProperty: 'embedding', 
  k: 5, 
  maxIterations: 50, 
  randomSeed: 42, 
  computeSilhouette: true
})
YIELD nodeId, communityId, silhouette
RETURN communityId as cluster, avg(silhouette) as avg_silhouette
ORDER BY cluster;
```

**Insight**: Showed that Clusters 0-3 have good silhouette scores (>0.5), indicating well-formed clusters, while Cluster 4 has a lower score (0.33), suggesting it might be less cohesive

### Functions with High Connectivity

```cypher
// Find functions with highest connectivity
MATCH (f:Function)
WHERE f.incoming_calls > 0 OR f.outgoing_calls > 0
RETURN f.name, f.cluster, f.incoming_calls, f.outgoing_calls, 
       f.incoming_calls + f.outgoing_calls as total_connectivity
ORDER BY total_connectivity DESC
LIMIT 10;
```

**Insight**: Identified the most connected functions in the codebase, which are likely to be critical components that might need special attention during maintenance

### Cluster Visualization

```cypher
MATCH p=(n:!Cluster)-[r]-(m:!Cluster) WHERE n.cluster = 0 AND n <> m RETURN p ORDER BY rand() LIMIT 200
UNION
MATCH p=(n:!Cluster)-[r]-(m:!Cluster) WHERE n.cluster = 1 AND n <> m   RETURN p ORDER BY rand()  LIMIT 200
UNION
MATCH p=(n:!Cluster)-[r]-(m:!Cluster)  WHERE n.cluster = 2 AND n <> m   RETURN p ORDER BY rand()  LIMIT 200
UNION
MATCH p=(n:!Cluster)-[r]-(m:!Cluster) WHERE n.cluster = 3 AND n <> m   RETURN p ORDER BY rand()  LIMIT 200
UNION
MATCH p=(n:!Cluster)-[r]-(m:!Cluster)  WHERE n.cluster = 4 AND n <> m   RETURN p ORDER BY rand()  LIMIT 200
;
```

**Insight**: Provided a visual representation of the clusters, showing how functions are grouped based on their characteristics
