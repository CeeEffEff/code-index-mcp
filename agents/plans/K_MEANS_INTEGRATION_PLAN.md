# K-Means Clustering Integration Plan for Neo4j Index Builder

## Overview

This document outlines a plan to integrate K-means clustering capabilities directly into the Neo4j index builder and manager. This integration will enable automatic code structure analysis during the index building process, providing valuable insights into the codebase organization and function characteristics.

## Current Architecture

The current Neo4j index builder and manager consist of:

1. **Neo4jIndexBuilder**: Responsible for building the Neo4j graph representation of the codebase
2. **Neo4jIndexManager**: Manages the lifecycle of the Neo4j-based index
3. **Neo4jIndexProvider**: Provides access to the index data

## Integration Goals

1. Add K-means clustering capabilities to the Neo4j index builder
2. Automatically compute function features during index building
3. Run clustering analysis after index building is complete
4. Store clustering results in the Neo4j database
5. Provide API access to clustering results

## Implementation Plan

### 1. Add Feature Computation to Neo4jIndexBuilder

Modify the `Neo4jIndexBuilder` class to compute and store the features needed for clustering:

```python
def _compute_function_features(self):
    """Compute numerical features for all Function nodes in the graph."""
    logger.info("Computing function features for clustering...")
    
    with self.driver.session() as session:
        # Count outgoing calls for each function
        session.run("""
            MATCH (f:Function)-[:CALLS]->(other:Function)
            WITH f, count(other) as outgoing_calls
            SET f.outgoing_calls = outgoing_calls
        """)
        
        # Count incoming calls for each function
        session.run("""
            MATCH (f:Function)<-[:CALLS]-(other:Function)
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
        
        # Create embedding vector for clustering
        session.run("""
            MATCH (f:Function)
            SET f.embedding = [
              toFloat(f.outgoing_calls), 
              toFloat(f.incoming_calls), 
              toFloat(f.arg_count),
              toFloat(f.file_line_count),
              toFloat(f.file_import_count)
            ]
        """)
        
        logger.info("Function features computed successfully")
```

### 2. Add K-Means Clustering to Neo4jIndexBuilder

Add a method to run K-means clustering using the Neo4j Graph Data Science library:

```python
def _run_kmeans_clustering(self, k=5, max_iterations=50, random_seed=42):
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
            
            # Run K-means clustering
            result = session.run(f"""
                CALL gds.kmeans.write('code-functions', {{
                  nodeProperty: 'embedding', 
                  k: {k}, 
                  maxIterations: {max_iterations}, 
                  randomSeed: {random_seed}, 
                  writeProperty: 'cluster',
                  computeSilhouette: true
                }})
                YIELD nodeCount, communityCount, silhouette
                RETURN nodeCount, communityCount, silhouette
            """)
            
            record = result.single()
            if record:
                logger.info(f"K-means clustering completed: {record['nodeCount']} nodes, "
                           f"{record['communityCount']} clusters, "
                           f"silhouette score: {record['silhouette']}")
            
            # Compute cluster statistics
            self._compute_cluster_statistics()
            
            # Drop graph projection to free memory
            session.run("CALL gds.graph.drop('code-functions')")
            
            return True
    except Exception as e:
        logger.error(f"Error running K-means clustering: {e}")
        return False
```

### 3. Add Cluster Statistics Computation

Add a method to compute and store statistics for each cluster:

```python
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
            WITH f.cluster as cluster,
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
                c.avg_file_imports = avg_imports
            WITH c
            MATCH (stats:ClusterStatistics {id: 'cluster_stats'})
            MERGE (stats)-[:HAS_CLUSTER]->(c)
            RETURN c.id, c.count
        """)
        
        clusters = [f"Cluster {record['c.id']}: {record['c.count']} functions" 
                   for record in result]
        
        logger.info(f"Computed statistics for {len(clusters)} clusters")
        logger.info(f"Clusters: {', '.join(clusters)}")
```

### 4. Modify the build_index Method

Update the `build_index` method to include feature computation and clustering:

```python
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
    
    # ... existing code ...
    
    try:
        # ... existing code for building the index ...
        
        # After building the index, compute features and run clustering if requested
        if run_clustering:
            logger.info("Computing features and running clustering...")
            self._compute_function_features()
            self._run_kmeans_clustering(k=k)
            
            # Update metadata to include clustering information
            metadata.clustering_k = k
            metadata.clustering_timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        
        # ... rest of existing code ...
        
        return True
        
    except Exception as e:
        logger.error(f"Error building Neo4j index: {e}")
        return False
```

### 5. Add Clustering Configuration to Neo4jIndexManager

Modify the `Neo4jIndexManager` class to include clustering configuration:

```python
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
```

### 6. Update the refresh_index Method

Modify the `refresh_index` method to include clustering configuration:

```python
def refresh_index(self, force: bool = False) -> bool:
    """Refresh the index."""
    with self._lock:
        if not self.index_builder:
            logger.error("Index builder not initialized")
            return False
        
        try:
            logger.info("Refreshing Neo4j index...")
            return self.index_builder.build_index(
                run_clustering=getattr(self, 'clustering_enabled', True),
                k=getattr(self, 'clustering_k', 5)
            )
            
        except Exception as e:
            logger.error(f"Failed to refresh index: {e}")
            return False
```

### 7. Add Cluster Query Methods to Neo4jIndexProvider

Add methods to the `Neo4jIndexProvider` class to query clustering results:

```python
def get_cluster_statistics(self) -> List[Dict[str, Any]]:
    """
    Get statistics for all clusters.
    
    Returns:
        List of cluster statistics dictionaries
    """
    try:
        with self.driver.session() as session:
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
            
            return [dict(record) for record in result]
            
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
            
            return [dict(record) for record in result]
            
    except Exception as e:
        logger.error(f"Error getting functions in cluster {cluster_id}: {e}")
        return []
```

### 8. Add Command-Line Interface for Clustering

Add command-line options to the existing CLI tools:

```python
def main():
    """Command-line interface for Neo4j index management."""
    parser = argparse.ArgumentParser(description="Neo4j Index Manager CLI")
    parser.add_argument("--project-path", required=True, help="Path to the project")
    parser.add_argument("--refresh", action="store_true", help="Refresh the index")
    parser.add_argument("--clustering", action="store_true", help="Run K-means clustering")
    parser.add_argument("--k", type=int, default=5, help="Number of clusters for K-means")
    parser.add_argument("--max-iterations", type=int, default=50, help="Maximum iterations for K-means")
    parser.add_argument("--show-clusters", action="store_true", help="Show cluster statistics")
    
    args = parser.parse_args()
    
    # Initialize Neo4j index manager
    manager = get_neo4j_index_manager()
    manager.set_project_path(args.project_path)
    manager.initialize()
    
    if args.clustering:
        manager.set_clustering_config(enabled=True, k=args.k, max_iterations=args.max_iterations)
    
    if args.refresh:
        print(f"Refreshing index for {args.project_path}...")
        success = manager.refresh_index()
        print(f"Index refresh {'successful' if success else 'failed'}")
    
    if args.show_clusters:
        provider = manager.get_provider()
        if provider:
            clusters = provider.get_cluster_statistics()
            print(f"\nCluster Statistics ({len(clusters)} clusters):")
            for cluster in clusters:
                print(f"Cluster {cluster['id']}: {cluster['count']} functions")
                print(f"  Avg Outgoing Calls: {cluster['avg_outgoing']:.2f}")
                print(f"  Avg Incoming Calls: {cluster['avg_incoming']:.2f}")
                print(f"  Avg Arguments: {cluster['avg_args']:.2f}")
                print(f"  Avg File Lines: {cluster['avg_lines']:.2f}")
                print(f"  Avg File Imports: {cluster['avg_imports']:.2f}")
                
                # Show top functions in each cluster
                functions = provider.get_functions_in_cluster(cluster['id'], limit=5)
                if functions:
                    print("  Top Functions:")
                    for func in functions:
                        print(f"    - {func['name']} (in: {func['incoming_calls']}, out: {func['outgoing_calls']})")
                print()
```

## Integration with Cross-File Function Calls Fix

This K-means clustering integration complements the cross-file function calls fix described in CROSS_FILE_CALLS_FIX.md. The improved cross-file function call detection will enhance the quality of the clustering by:

1. Providing more accurate `incoming_calls` and `outgoing_calls` metrics
2. Enabling better identification of utility functions that are called from multiple files
3. Improving the detection of core service functions vs. specialized functions

The implementation order should be:

1. First implement the cross-file function calls fix
2. Then implement the K-means clustering integration
3. Test both features together to ensure they work correctly

## Testing Plan

1. **Unit Tests**:
   - Test feature computation with different function signatures
   - Test clustering with different k values
   - Test cluster statistics computation

2. **Integration Tests**:
   - Test the end-to-end index building with clustering
   - Verify that clustering results are stored correctly
   - Test the API for querying clustering results

3. **Performance Tests**:
   - Measure the impact of clustering on index building time
   - Test with different codebase sizes to ensure scalability

## Conclusion

Integrating K-means clustering into the Neo4j index builder and manager will provide valuable insights into the codebase structure and organization. This integration will enable automatic code analysis during the index building process, helping developers understand the characteristics of different functions and identify potential areas for refactoring or optimization.

The implementation plan outlined in this document provides a comprehensive approach to adding clustering capabilities to the existing Neo4j index builder and manager, with a focus on maintainability, performance, and usability.
