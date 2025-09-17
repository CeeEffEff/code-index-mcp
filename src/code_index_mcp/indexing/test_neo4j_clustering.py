#!/usr/bin/env python3
"""
Test script for Neo4j clustering and cross-file call detection.

This script tests the Neo4j clustering and cross-file call detection functionality
by building an index for a sample project and verifying the results.
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path

from code_index_mcp.indexing.neo4j_index_manager import get_neo4j_index_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def test_cross_file_calls(provider):
    """Test cross-file call detection."""
    logger.info("Testing cross-file call detection...")
    
    # Get cross-file calls
    calls = provider.get_cross_file_calls(limit=10)
    
    if not calls:
        logger.warning("No cross-file calls detected. This is unusual for a real-world codebase.")
        return False
    
    logger.info(f"Detected {len(calls)} cross-file calls")
    for i, call in enumerate(calls[:3], 1):
        logger.info(f"{i}. {call['caller_name']} -> {call['called_name']}")
        logger.info(f"   Caller File: {call['caller_file']}")
        logger.info(f"   Called File: {call['called_file']}")
    
    # Get functions with most cross-file calls
    functions = provider.get_functions_with_most_cross_file_calls(limit=5)
    
    outgoing = functions.get("outgoing", [])
    incoming = functions.get("incoming", [])
    
    if outgoing:
        logger.info(f"Functions with most outgoing cross-file calls: {len(outgoing)}")
        for i, func in enumerate(outgoing[:2], 1):
            logger.info(f"{i}. {func['name']} ({func['outgoing_cross_file_calls']} calls)")
    
    if incoming:
        logger.info(f"Functions with most incoming cross-file calls: {len(incoming)}")
        for i, func in enumerate(incoming[:2], 1):
            logger.info(f"{i}. {func['name']} ({func['incoming_cross_file_calls']} calls)")
    
    return len(calls) > 0


def test_clustering(provider, k=5):
    """Test K-means clustering."""
    logger.info("Testing K-means clustering...")
    
    # Get cluster statistics
    clusters = provider.get_cluster_statistics()
    
    if not clusters:
        logger.warning("No clusters detected.")
        return False
    
    logger.info(f"Detected {len(clusters)} clusters")
    
    # Check if we have the expected number of clusters
    if len(clusters) != k:
        logger.warning(f"Expected {k} clusters, but got {len(clusters)}")
    
    # Display cluster statistics
    for cluster in clusters:
        logger.info(f"Cluster {cluster['id']}: {cluster['count']} functions")
        logger.info(f"  Avg Outgoing Calls: {cluster.get('avg_outgoing', 0):.2f}")
        logger.info(f"  Avg Incoming Calls: {cluster.get('avg_incoming', 0):.2f}")
    
    # Get functions in each cluster
    for cluster_id in range(len(clusters)):
        functions = provider.get_functions_in_cluster(cluster_id, limit=5)
        logger.info(f"Cluster {cluster_id}: {len(functions)} functions")
        for i, func in enumerate(functions[:2], 1):
            logger.info(f"  {i}. {func['name']} (in: {func.get('incoming_calls', 0)}, out: {func.get('outgoing_calls', 0)})")
    
    return True


def main():
    """Main test function."""
    parser = argparse.ArgumentParser(description="Test Neo4j clustering and cross-file call detection")
    parser.add_argument("--project-path", required=True, help="Path to the project")
    parser.add_argument("--k", type=int, default=5, help="Number of clusters for K-means")
    parser.add_argument("--max-iterations", type=int, default=50, help="Maximum iterations for K-means")
    parser.add_argument("--skip-refresh", action="store_true", help="Skip index refresh")
    
    # Neo4j connection options
    # neo4j_group = parser.add_argument_group("Neo4j Connection Options")
    parser.add_argument("--neo4j-uri", default="bolt://localhost:7687", help="Neo4j URI")
    parser.add_argument("--neo4j-user", default="neo4j", help="Neo4j username")
    parser.add_argument("--neo4j-password", default="password", help="Neo4j password")
    parser.add_argument("--neo4j-database", default="neo4j", help="Neo4j database name")
    parser.add_argument("--config-path", help="Path to Neo4j configuration file", default=None)
    
    args = parser.parse_args()
    
    # Validate project path
    project_path = args.project_path
    if not os.path.isdir(project_path):
        logger.error(f"Project path does not exist: {project_path}")
        sys.exit(1)
    
    logger.info(f"Testing with project: {project_path}")
    
    # Initialize Neo4j index manager
    manager = get_neo4j_index_manager()
    
    # Set project path and config path if provided
    if args.config_path:
        manager.config_path = args.config_path
        
    manager.set_project_path(project_path)
    
    # Set Neo4j connection configuration
    manager.set_neo4j_config(
        uri=args.neo4j_uri,
        user=args.neo4j_user,
        password=args.neo4j_password,
        database=args.neo4j_database
    )
    
    if not manager.initialize():
        logger.error("Failed to initialize Neo4j index manager")
        sys.exit(1)
    
    # Configure clustering
    manager.set_clustering_config(enabled=True, k=args.k, max_iterations=args.max_iterations)
    logger.info(f"Configured clustering with k={args.k}, max_iterations={args.max_iterations}")
    
    # Refresh index if needed
    if not args.skip_refresh:
        logger.info(f"Refreshing index for {project_path}...")
        start_time = time.time()
        success = manager.refresh_index()
        elapsed = time.time() - start_time
        logger.info(f"Index refresh {'successful' if success else 'failed'} in {elapsed:.2f}s")
        
        if not success:
            logger.error("Failed to refresh index")
            sys.exit(1)
    
    # Get provider
    provider = manager.get_provider()
    if not provider:
        logger.error("Failed to get Neo4j index provider")
        sys.exit(1)
    
    # Show index status
    status = manager.get_index_status()
    logger.info(f"Index Status: {status['status']}")
    logger.info(f"Files: {status.get('file_count', 0)}")
    logger.info(f"Symbols: {status.get('symbol_count', 0)}")
    logger.info(f"Functions: {status.get('function_count', 0)}")
    logger.info(f"Clusters: {status.get('cluster_count', 0)}")
    
    if "clustering" in status:
        clustering = status["clustering"]
        logger.info(f"Clustering: k={clustering['k']}, timestamp={clustering['timestamp']}")
    
    # Test cross-file call detection
    cross_file_success = test_cross_file_calls(provider)
    
    # Test clustering
    clustering_success = test_clustering(provider, args.k)
    
    # Report results
    logger.info("\nTest Results:")
    logger.info(f"Cross-File Call Detection: {'PASS' if cross_file_success else 'FAIL'}")
    logger.info(f"K-means Clustering: {'PASS' if clustering_success else 'FAIL'}")
    
    if cross_file_success and clustering_success:
        logger.info("All tests passed!")
        return 0
    else:
        logger.warning("Some tests failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
