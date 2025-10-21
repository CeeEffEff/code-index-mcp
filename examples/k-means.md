# K-Means Clustering for Code Repository Analysis

## Step 1: Create Numerical Features for Clustering

We'll use these features for each Function node:

1. **Outgoing Calls Count**: Number of other functions this function calls
2. **Incoming Calls Count**: Number of other functions that call this function
3. **Argument Count**: Number of parameters in the function signature
4. **File Line Count**: Number of lines in the file containing the function (proxy for module complexity)
5. **Import Count**: Number of imports in the file containing the function (proxy for dependencies)

These features capture different aspects of function complexity and importance:
- Functions with high outgoing calls are likely complex orchestrators
- Functions with high incoming calls are likely core utilities
- Functions with many arguments may have complex interfaces
- Functions in large files may be part of complex modules
- Functions in files with many imports may have many external dependencies

## Step 2: Store Features as Node Properties

We'll need to create these properties on the Function nodes to use with the k-means clustering algorithm:

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

// Count arguments for each function
MATCH (f:Function)
WHERE f.signature IS NOT NULL
SET f.arg_count = CASE true
  WHEN f.type = "file" THEN 0
  WHEN f.signature CONTAINS "():" THEN 0
  WHEN f.signature CONTAINS "," THEN size(split(f.signature, ","))
  ELSE 1
END;

// Add file properties to functions
MATCH (file:File)-[:CONTAINS]->(f:Function)
SET f.file_line_count = CASE WHEN file.line_count IS NOT NULL THEN file.line_count ELSE 0 END,
    f.file_import_count = CASE WHEN file.imports IS NOT NULL THEN size(file.imports) ELSE 0 END;
```

## Step 3: Create Embedding Vector for Clustering

K-means clustering requires a vector of numerical values. We'll create an embedding array property:

```cypher
MATCH (f:Function)
SET f.embedding = [
  toFloat(f.outgoing_calls), 
  toFloat(f.incoming_calls), 
  toFloat(f.arg_count),
  toFloat(f.file_line_count),
  toFloat(f.file_import_count)
];
```

## Step 4: Run K-Means Clustering

We'll use the neo4j-gds k_means_clustering tool to group similar functions based on these features:

```cypher
// Create graph projection for GDS
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
);

// Run k-means clustering with k=5
CALL gds.kmeans.stream('code-functions', {
  nodeProperty: 'embedding', 
  k: 5, 
  maxIterations: 50, 
  randomSeed: 42, 
  computeSilhouette: true
})
YIELD nodeId, communityId, distanceFromCentroid, silhouette
RETURN communityId, count(*) as count, avg(silhouette) as avg_silhouette
ORDER BY count DESC;
```

## Step 5: Analyze and Visualize Results

We'll examine the resulting clusters to understand what types of functions are grouped together:

```cypher
// View cluster distribution
MATCH (f:Function)
RETURN f.cluster as cluster, count(*) as count
ORDER BY count DESC;

// View representative functions from each cluster
MATCH (f:Function)
RETURN f.cluster as cluster, f.name as function_name, 
       f.outgoing_calls, f.incoming_calls, f.arg_count,
       f.file_line_count, f.file_import_count
ORDER BY cluster, f.incoming_calls + f.outgoing_calls DESC
LIMIT 25;
```

This analysis will help identify:
- Core utility functions vs. specialized functions
- Functions with similar usage patterns
- Potential code organization improvements
- Outliers that might need refactoring

## Step 6: Cluster Characteristics and Interpretation

After running the k-means clustering with k=5, we identified the following clusters:

### Cluster 0: Simple Utility Functions (594 functions, 18.3%)
- **Average File Line Count**: 55 (smallest)
- **Average Import Count**: 7.6 (smallest)
- **Average Args**: 2.1
- **Average Calls**: 0.19 (lowest)
- **Representative Functions**: `read_file`, `create_new_file`, `split_markdown_chunks`
- **Description**: Small utility functions in small files with few imports, typically with low connectivity to other functions.

### Cluster 1: Medium Complexity Service Functions (614 functions, 18.9%)
- **Average File Line Count**: 143
- **Average Import Count**: 14.6
- **Average Args**: 2.3
- **Average Calls**: 0.29
- **Representative Functions**: `TechHealthService.process_crawl_file`, `FirestorePaginator.paginate`
- **Description**: Medium-sized service functions with moderate complexity and moderate connectivity.

### Cluster 2: Complex Processing Functions (888 functions, 27.3%)
- **Average File Line Count**: 253
- **Average Import Count**: 21.1
- **Average Args**: 2.5
- **Average Calls**: 0.36
- **Representative Functions**: `parse_schemaorg_pdp_results`, `SpiderService.process_company_file`
- **Description**: Complex processing functions in larger files with more imports and higher connectivity.

### Cluster 3: Core Service Functions (851 functions, 26.2%)
- **Average File Line Count**: 551
- **Average Import Count**: 31.9
- **Average Args**: 2.0
- **Average Calls**: 0.43
- **Representative Functions**: `get_clean_db_instance`, `FirestoreDatabase` methods
- **Description**: Core service functions in large files with many imports and high connectivity.

### Cluster 4: Framework/Infrastructure Functions (300 functions, 9.2%)
- **Average File Line Count**: 1024 (largest)
- **Average Import Count**: 41.2 (largest)
- **Average Args**: 2.4
- **Average Calls**: 0.46 (highest)
- **Representative Functions**: `FirestoreDatabase` methods in very large files
- **Description**: Framework or infrastructure functions in very large files with the most imports and highest connectivity.

## Step 7: Silhouette Analysis

The silhouette score measures how well-separated the clusters are. Our analysis showed:

| Cluster | Count | Avg Silhouette |
|---------|-------|---------------|
| 0       | 594   | 0.632         |
| 1       | 614   | 0.545         |
| 2       | 888   | 0.514         |
| 3       | 851   | 0.559         |
| 4       | 300   | 0.330         |

Clusters 0-3 have good silhouette scores (>0.5), indicating well-formed clusters. Cluster 4 has a lower score, suggesting it might be less cohesive or contain more outliers.

## Step 8: Key Insights and Applications

1. **File Size Correlation**: The clustering shows a strong correlation between file size (line count) and import count, suggesting that larger files tend to have more dependencies.

2. **Function Complexity Gradient**: The clusters form a clear gradient from simple utility functions (Cluster 0) to complex framework functions (Cluster 4).

3. **Function Call Patterns**: As noted in function-calls-oddity.md, the graph doesn't show many cross-file function calls, which may affect the clustering quality. Despite this limitation, the clustering still reveals meaningful patterns based on the other features.

4. **Potential Applications**:
   - **Code Organization**: The clusters can inform better code organization by grouping similar functions together.
   - **Refactoring Targets**: Clusters with very large files and high connectivity might be candidates for refactoring.
   - **Documentation Focus**: More complex clusters might need more thorough documentation.
   - **Maintenance Planning**: Understanding which functions belong to which clusters can help prioritize maintenance efforts.
