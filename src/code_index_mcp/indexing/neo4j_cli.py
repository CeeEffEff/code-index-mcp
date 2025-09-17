#!/usr/bin/env python3
"""
Command-line interface for Neo4j index management.

This module provides a command-line interface for managing the Neo4j-based code index,
including clustering and cross-file call analysis.
"""

import argparse
import logging
import os
import sys
from typing import Dict, Any, List

from .neo4j_index_manager import get_neo4j_index_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def display_cluster_statistics(clusters: List[Dict[str, Any]]):
    """Display cluster statistics in a formatted way."""
    if not clusters:
        print("No clusters found.")
        return
    
    print(f"\nCluster Statistics ({len(clusters)} clusters):")
    for cluster in clusters:
        print(f"Cluster {cluster['id']}: {cluster['count']} functions")
        print(f"  Avg Outgoing Calls: {cluster['avg_outgoing']:.2f}")
        print(f"  Avg Incoming Calls: {cluster['avg_incoming']:.2f}")
        print(f"  Avg Arguments: {cluster['avg_args']:.2f}")
        print(f"  Avg File Lines: {cluster['avg_lines']:.2f}")
        print(f"  Avg File Imports: {cluster['avg_imports']:.2f}")
        print()


def display_functions_in_cluster(functions: List[Dict[str, Any]], cluster_id: int):
    """Display functions in a cluster in a formatted way."""
    if not functions:
        print(f"No functions found in cluster {cluster_id}.")
        return
    
    print(f"\nTop Functions in Cluster {cluster_id} ({len(functions)} functions):")
    for i, func in enumerate(functions[:10], 1):
        print(f"{i}. {func['name']}")
        print(f"   ID: {func['id']}")
        print(f"   Incoming Calls: {func['incoming_calls']}")
        print(f"   Outgoing Calls: {func['outgoing_calls']}")
        print(f"   Arguments: {func['arg_count']}")
        print()
    
    if len(functions) > 10:
        print(f"... and {len(functions) - 10} more functions")


def display_cross_file_calls(calls: List[Dict[str, Any]]):
    """Display cross-file calls in a formatted way."""
    if not calls:
        print("No cross-file calls found.")
        return
    
    print(f"\nCross-File Calls ({len(calls)} calls):")
    for i, call in enumerate(calls[:10], 1):
        print(f"{i}. {call['caller_name']} -> {call['called_name']}")
        print(f"   Caller File: {call['caller_file']}")
        print(f"   Called File: {call['called_file']}")
        print()
    
    if len(calls) > 10:
        print(f"... and {len(calls) - 10} more calls")


def display_functions_with_most_cross_file_calls(functions: Dict[str, List[Dict[str, Any]]]):
    """Display functions with most cross-file calls in a formatted way."""
    outgoing = functions.get("outgoing", [])
    incoming = functions.get("incoming", [])
    
    if not outgoing and not incoming:
        print("No functions with cross-file calls found.")
        return
    
    if outgoing:
        print(f"\nFunctions with Most Outgoing Cross-File Calls ({len(outgoing)} functions):")
        for i, func in enumerate(outgoing[:5], 1):
            print(f"{i}. {func['name']}")
            print(f"   ID: {func['id']}")
            print(f"   Outgoing Cross-File Calls: {func['outgoing_cross_file_calls']}")
            print(f"   Total Outgoing Calls: {func['outgoing_calls']}")
            print()
    
    if incoming:
        print(f"\nFunctions with Most Incoming Cross-File Calls ({len(incoming)} functions):")
        for i, func in enumerate(incoming[:5], 1):
            print(f"{i}. {func['name']}")
            print(f"   ID: {func['id']}")
            print(f"   Incoming Cross-File Calls: {func['incoming_cross_file_calls']}")
            print(f"   Total Incoming Calls: {func['incoming_calls']}")
            print()


def main():
    """Command-line interface for Neo4j index management."""
    parser = argparse.ArgumentParser(description="Neo4j Index Manager CLI")
    parser.add_argument("--project-path", required=True, help="Path to the project")
    parser.add_argument("--refresh", action="store_true", help="Refresh the index")
    
    # Neo4j connection options
    neo4j_group = parser.add_argument_group("Neo4j Connection Options")
    neo4j_group.add_argument("--neo4j-uri", default="bolt://localhost:7687", help="Neo4j URI")
    neo4j_group.add_argument("--neo4j-user", default="neo4j", help="Neo4j username")
    neo4j_group.add_argument("--neo4j-password", default="password", help="Neo4j password")
    neo4j_group.add_argument("--neo4j-database", default="neo4j", help="Neo4j database name")
    neo4j_group.add_argument("--config-path", help="Path to Neo4j configuration file", default=None)
    
    # Clustering options
    clustering_group = parser.add_argument_group("Clustering Options")
    clustering_group.add_argument("--clustering", action="store_true", help="Run K-means clustering")
    clustering_group.add_argument("--k", type=int, default=5, help="Number of clusters for K-means")
    clustering_group.add_argument("--max-iterations", type=int, default=50, help="Maximum iterations for K-means")
    clustering_group.add_argument("--show-clusters", action="store_true", help="Show cluster statistics")
    clustering_group.add_argument("--cluster-id", type=int, help="Show functions in a specific cluster")
    
    # Cross-file call options
    cross_file_group = parser.add_argument_group("Cross-File Call Options")
    cross_file_group.add_argument("--show-cross-file-calls", action="store_true", help="Show cross-file function calls")
    cross_file_group.add_argument("--limit", type=int, default=100, help="Limit for query results")
    cross_file_group.add_argument("--show-top-cross-file-functions", action="store_true", help="Show functions with most cross-file calls")
    
    args = parser.parse_args()
    
    # Initialize Neo4j index manager
    manager = get_neo4j_index_manager()

    # Set project path and config path if provided
    if args.config_path:
        manager.config_path = args.config_path
        
    manager.set_project_path(args.project_path)
    
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
    
    if args.clustering:
        manager.set_clustering_config(enabled=True, k=args.k, max_iterations=args.max_iterations)
        print(f"Configured clustering with k={args.k}, max_iterations={args.max_iterations}")
    
    if args.refresh:
        print(f"Refreshing index for {args.project_path}...")
        success = manager.refresh_index()
        print(f"Index refresh {'successful' if success else 'failed'}")
    
    provider = manager.get_provider()
    if not provider:
        logger.error("Failed to get Neo4j index provider")
        sys.exit(1)
    
    # Show index status
    status = manager.get_index_status()
    print("\nIndex Status:")
    print(f"  Status: {status['status']}")
    print(f"  Files: {status.get('file_count', 0)}")
    print(f"  Symbols: {status.get('symbol_count', 0)}")
    print(f"  Classes: {status.get('class_count', 0)}")
    print(f"  Functions: {status.get('function_count', 0)}")
    print(f"  Clusters: {status.get('cluster_count', 0)}")
    
    if "clustering" in status:
        clustering = status["clustering"]
        print(f"  Clustering: k={clustering['k']}, timestamp={clustering['timestamp']}")
    
    # Show cluster statistics
    if args.show_clusters:
        clusters = provider.get_cluster_statistics()
        display_cluster_statistics(clusters)
    
    # Show functions in a specific cluster
    if args.cluster_id is not None:
        functions = provider.get_functions_in_cluster(args.cluster_id, limit=args.limit)
        display_functions_in_cluster(functions, args.cluster_id)
    
    # Show cross-file calls
    if args.show_cross_file_calls:
        calls = provider.get_cross_file_calls(limit=args.limit)
        display_cross_file_calls(calls)
    
    # Show functions with most cross-file calls
    if args.show_top_cross_file_functions:
        functions = provider.get_functions_with_most_cross_file_calls(limit=args.limit)
        display_functions_with_most_cross_file_calls(functions)


if __name__ == "__main__":
    main()
