# K-Means Clustering Query for Neo4j Graph Data Science

This document contains the complete query sequence for running k-means clustering on a code repository graph in Neo4j. The queries prepare the data, run the clustering algorithm, and analyze the results.

## Step 1: Prepare Node Properties for Clustering

First, we need to create numerical properties on the Function nodes that will be used for clustering:

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

Note: The original query used `indexOf()` and `substring()` functions for argument counting, but we found that these functions weren't available in our Neo4j instance. We adapted the query to use a simpler CASE statement approach that works with standard Neo4j functions.

## Step 2: Create Graph Projection for GDS

Before running the clustering algorithm, we need to create a graph projection in the Graph Data Science library:

```cypher
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
```

This projection includes only Function nodes and CALLS relationships, with the embedding property that contains our feature vector for clustering.

## Step 3: Run K-Means Clustering

Now we can run the k-means clustering algorithm on our graph projection:

```cypher
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

Parameters to adjust:
- `k`: Number of clusters (try values between 3-10)
- `randomSeed`: Set for reproducible results
- `maxIterations`: Maximum number of iterations (default is 10, we used 50)
- `computeSilhouette`: Calculate silhouette score to evaluate clustering quality

Note: We found that the syntax for running k-means had changed from the original documentation. The updated syntax uses `gds.kmeans.stream` instead of `gds.beta.kmeans.write`.

## Step 4: Analyze Clustering Results

After running the clustering algorithm, we can analyze the results:

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

Our analysis revealed the following cluster characteristics:

| Cluster | Count | % of Total | Avg Lines | Avg Imports | Avg Args | Avg Calls | Description |
|---------|-------|------------|-----------|-------------|----------|-----------|-------------|
| 0       | 594   | 18.3%      | 55        | 7.6         | 2.1      | 0.19      | Simple Utility Functions |
| 1       | 614   | 18.9%      | 143       | 14.6        | 2.3      | 0.29      | Medium Complexity Service Functions |
| 2       | 888   | 27.3%      | 253       | 21.1        | 2.5      | 0.36      | Complex Processing Functions |
| 3       | 851   | 26.2%      | 551       | 31.9        | 2.0      | 0.43      | Core Service Functions |
| 4       | 300   | 9.2%       | 1024      | 41.2        | 2.4      | 0.46      | Framework/Infrastructure Functions |

The silhouette scores for each cluster were:

| Cluster | Avg Silhouette |
|---------|----------------|
| 0       | 0.632          |
| 1       | 0.545          |
| 2       | 0.514          |
| 3       | 0.559          |
| 4       | 0.330          |

Clusters 0-3 have good silhouette scores (>0.5), indicating well-formed clusters. Cluster 4 has a lower score, suggesting it might be less cohesive or contain more outliers.

## Step 5: Visualize Clusters

To visualize the clusters, we can use Neo4j's built-in visualization capabilities:

```cypher
// Create a subgraph of functions colored by cluster
MATCH (f:Function)
WHERE f.cluster IS NOT NULL AND (f.incoming_calls > 0 OR f.outgoing_calls > 0)
RETURN f.name, f.cluster, f.incoming_calls, f.outgoing_calls, f.arg_count
LIMIT 100;
```

This query returns a sample of functions with their cluster assignments and key metrics, which can be visualized to see how the clusters are distributed.

## Step 6: Write Cluster Assignments Back to Nodes (Optional)

If you want to permanently store the cluster assignments on the nodes:

```cypher
CALL gds.kmeans.write('code-functions', {
  nodeProperty: 'embedding', 
  k: 5, 
  maxIterations: 50, 
  randomSeed: 42, 
  writeProperty: 'cluster'
});
```

This writes the cluster assignments back to the nodes as a property called 'cluster', which can be used for further analysis or visualization.

## Step 7: Clean Up (Optional)

If you want to remove the properties and graph projection after analysis:

```cypher
// Remove properties
MATCH (f:Function)
REMOVE f.outgoing_calls, f.incoming_calls, f.arg_count, 
       f.file_line_count, f.file_import_count, f.embedding, f.cluster;

// Drop graph projection
CALL gds.graph.drop('code-functions');
```

## Execution Results

When we executed this query sequence on our code repository graph:

1. We successfully created numerical properties for 3,247 Function nodes
2. We created a graph projection with 3,247 nodes and 1,121 relationships
3. The k-means clustering algorithm grouped the functions into 5 clusters
4. The analysis revealed a clear gradient of complexity across the clusters
5. The silhouette analysis showed that most clusters were well-formed

The clustering results provide valuable insights into the structure of the codebase, identifying different types of functions based on their characteristics. This can inform code organization, refactoring efforts, and maintenance planning.
