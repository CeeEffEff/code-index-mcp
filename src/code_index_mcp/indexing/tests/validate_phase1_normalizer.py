#!/usr/bin/env python3
"""
Validation script for Phase 1: Symbol ID Normalization

This script:
1. Rebuilds the Neo4j index with the new normalizer
2. Runs validation queries to confirm cross-file calls are detected
3. Verifies no orphaned placeholder symbols remain
4. Checks that venv:// and stdlib:// prefixes are being used

Expected results:
- Cross-file calls: ≥20 (target: 400% improvement from ~0-5)
- Orphaned symbols: 0
- Prefixed symbols: Should see venv:// and stdlib:// prefixes
"""

import sys
from pathlib import Path

# Add project root to Python path
# validate_phase1_normalizer.py -> tests/ -> indexing/ -> code_index_mcp/ -> src/ -> project_root/
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from neo4j import GraphDatabase
from code_index_mcp.indexing.neo4j_index_builder import Neo4jIndexBuilder
import json


def get_neo4j_connection():
    """Get Neo4j connection details from neo4j_config.json"""
    config_path = project_root / "neo4j_config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"Neo4j config not found at {config_path}")
    
    with open(config_path) as f:
        config = json.load(f)
    
    return config["uri"], config["user"], config["password"]


def rebuild_index(project_path: Path):
    """Rebuild the Neo4j index for the given project"""
    print(f"\n{'='*80}")
    print(f"REBUILDING INDEX FOR: {project_path}")
    print(f"{'='*80}\n")
    
    # Get Neo4j connection details
    uri, username, password = get_neo4j_connection()
    
    # Create index builder with venv path
    venv_path = project_root / ".venv"
    builder = Neo4jIndexBuilder(
        project_path=str(project_path),
        neo4j_uri=uri,
        neo4j_user=username,
        neo4j_password=password,
        venv_path=str(venv_path) if venv_path.exists() else None
    )
    
    # Build the index (disable clustering for validation)
    print("Starting index build...")
    builder.build_index(run_clustering=False)
    print("✅ Index build complete!\n")


def run_validation_queries():
    """Run validation queries to check Phase 1 implementation"""
    print(f"\n{'='*80}")
    print("RUNNING VALIDATION QUERIES")
    print(f"{'='*80}\n")
    
    uri, username, password = get_neo4j_connection()
    driver = GraphDatabase.driver(uri, auth=(username, password))
    
    results = {}
    
    try:
        with driver.session() as session:
            # Query 1: Count cross-file calls
            print("1. Checking cross-file function calls...")
            result = session.run("""
                MATCH (caller_file:File)-[:CONTAINS]->(caller:Symbol)-[:CALLS]->(called:Symbol)<-[:CONTAINS]-(called_file:File)
                WHERE caller_file.path <> called_file.path
                RETURN count(*) as cross_file_calls
            """)
            cross_file_calls = result.single()["cross_file_calls"]
            results["cross_file_calls"] = cross_file_calls
            print(f"   ✅ Found {cross_file_calls} cross-file calls")
            print(f"   Target: ≥20 (400% improvement from baseline ~0-5)")
            print(f"   Status: {'✅ PASS' if cross_file_calls >= 20 else '❌ FAIL'}\n")
            
            # Query 2: Check for orphaned symbols
            print("2. Checking for orphaned placeholder symbols...")
            result = session.run("""
                MATCH (s:Symbol)
                WHERE s.line = -1 AND NOT ()-[:CALLS]->(s)
                RETURN count(*) as orphaned_symbols
            """)
            orphaned = result.single()["orphaned_symbols"]
            results["orphaned_symbols"] = orphaned
            print(f"   ✅ Found {orphaned} orphaned symbols")
            print(f"   Target: 0")
            print(f"   Status: {'✅ PASS' if orphaned == 0 else '⚠️  WARNING'}\n")
            
            # Query 3: Check for venv:// and stdlib:// prefixes
            print("3. Checking for venv:// and stdlib:// prefixed symbols...")
            result = session.run("""
                MATCH (s:Symbol)
                WHERE s.qualified_name STARTS WITH 'venv://' OR s.qualified_name STARTS WITH 'stdlib://'
                RETURN s.qualified_name as qname, s.type as stype, 
                       CASE 
                         WHEN s.qualified_name STARTS WITH 'venv://' THEN 'venv'
                         WHEN s.qualified_name STARTS WITH 'stdlib://' THEN 'stdlib'
                       END as prefix_type
                ORDER BY prefix_type, qname
                LIMIT 20
            """)
            prefixed_symbols = list(result)
            results["prefixed_symbols_count"] = len(prefixed_symbols)
            
            if prefixed_symbols:
                print(f"   ✅ Found {len(prefixed_symbols)} prefixed symbols (showing first 20)")
                for record in prefixed_symbols[:10]:
                    print(f"      [{record['prefix_type']}] {record['qname']} ({record['stype']})")
                if len(prefixed_symbols) > 10:
                    print(f"      ... and {len(prefixed_symbols) - 10} more")
            else:
                print("   ❌ No prefixed symbols found")
            print(f"   Status: {'✅ PASS' if len(prefixed_symbols) > 0 else '❌ FAIL'}\n")
            
            # Query 4: Sample cross-file calls with details
            print("4. Sample cross-file call chains (first 10)...")
            result = session.run("""
                MATCH (caller_file:File)-[:CONTAINS]->(caller:Symbol)-[:CALLS]->(called:Symbol)<-[:CONTAINS]-(called_file:File)
                WHERE caller_file.path <> called_file.path
                RETURN 
                    caller_file.path as caller_file,
                    caller.qualified_name as caller_name,
                    called_file.path as called_file,
                    called.qualified_name as called_name
                ORDER BY caller_file, caller_name
                LIMIT 10
            """)
            call_chains = list(result)
            results["sample_call_chains"] = len(call_chains)
            
            if call_chains:
                print(f"   ✅ Found {len(call_chains)} sample call chains:")
                for record in call_chains:
                    print(f"\n      Caller: {record['caller_file']}")
                    print(f"              {record['caller_name']}")
                    print(f"      ↓ CALLS")
                    print(f"      Called: {record['called_file']}")
                    print(f"              {record['called_name']}")
            else:
                print("   ❌ No call chains found")
            
    finally:
        driver.close()
    
    return results


def print_summary(results: dict):
    """Print validation summary"""
    print(f"\n{'='*80}")
    print("VALIDATION SUMMARY")
    print(f"{'='*80}\n")
    
    cross_file_calls = results.get("cross_file_calls", 0)
    orphaned = results.get("orphaned_symbols", 0)
    prefixed = results.get("prefixed_symbols_count", 0)
    
    # Calculate pass/fail
    cross_file_pass = cross_file_calls >= 20
    orphaned_pass = orphaned == 0
    prefixed_pass = prefixed > 0
    
    all_pass = cross_file_pass and orphaned_pass and prefixed_pass
    
    print(f"Cross-file calls:     {cross_file_calls:>4} (target: ≥20)  {'✅ PASS' if cross_file_pass else '❌ FAIL'}")
    print(f"Orphaned symbols:     {orphaned:>4} (target: 0)    {'✅ PASS' if orphaned_pass else '⚠️  WARNING'}")
    print(f"Prefixed symbols:     {prefixed:>4} (target: >0)   {'✅ PASS' if prefixed_pass else '❌ FAIL'}")
    
    print(f"\n{'='*80}")
    if all_pass:
        print("🎉 PHASE 1 VALIDATION: ✅ ALL CHECKS PASSED")
        print("Symbol ID Normalization is working correctly!")
        print("Ready to proceed to Phase 2: Module-Level Call Tracking")
    else:
        print("⚠️  PHASE 1 VALIDATION: SOME CHECKS FAILED")
        print("Review the results above and investigate any failures.")
    print(f"{'='*80}\n")
    
    return all_pass


def main():
    """Main validation flow"""
    print("\n" + "="*80)
    print("PHASE 1 VALIDATION: Symbol ID Normalization")
    print("="*80)
    
    # Use the test sample Python project
    test_project = project_root / "test" / "sample-projects" / "python"
    
    if not test_project.exists():
        print(f"❌ Test project not found at: {test_project}")
        print("Please ensure the test sample projects are available.")
        return False
    
    print(f"\nTest project: {test_project}")
    print(f"Project root: {project_root}")
    
    # Step 1: Rebuild index
    try:
        rebuild_index(test_project)
    except Exception as e:
        print(f"❌ Error rebuilding index: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Step 2: Run validation queries
    try:
        results = run_validation_queries()
    except Exception as e:
        print(f"❌ Error running validation queries: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Step 3: Print summary
    success = print_summary(results)
    
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
