"""Manual verification script for SymbolIDNormalizer."""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from code_index_mcp.indexing.utils.symbol_id_normalizer import SymbolIDNormalizer


def test_normalizer():
    """Manual test of SymbolIDNormalizer functionality."""
    print("Testing SymbolIDNormalizer...")
    
    # Get project root (4 levels up from this file)
    project_root = str(Path(__file__).parent.parent.parent.parent.parent)
    venv_root = os.path.join(project_root, ".venv")
    
    print(f"\nProject root: {project_root}")
    print(f"Venv root: {venv_root}")
    
    normalizer = SymbolIDNormalizer(project_root, venv_root)
    
    # Test 1: Project file
    print("\n=== Test 1: Project File ===")
    project_file = os.path.join(project_root, "src", "code_index_mcp", "server.py")
    normalized = normalizer.normalize_path(project_file)
    symbol_id = normalizer.create_symbol_id(project_file, "main")
    print(f"Original: {project_file}")
    print(f"Normalized: {normalized}")
    print(f"Symbol ID: {symbol_id}")
    assert normalized == "src/code_index_mcp/server.py"
    assert symbol_id == "src/code_index_mcp/server.py::main"
    print("✓ PASS")
    
    # Test 2: Stdlib file
    print("\n=== Test 2: Standard Library File ===")
    import logging
    if logging.__file__:
        normalized = normalizer.normalize_path(logging.__file__)
        symbol_id = normalizer.create_symbol_id(logging.__file__, "Logger")
        print(f"Original: {logging.__file__}")
        print(f"Normalized: {normalized}")
        print(f"Symbol ID: {symbol_id}")
        assert normalized.startswith("stdlib://")
        assert "::Logger" in symbol_id
        print("✓ PASS")
    
    # Test 3: Consistency
    print("\n=== Test 3: Consistency ===")
    normalizer2 = SymbolIDNormalizer(project_root, venv_root)
    normalized1 = normalizer.normalize_path(project_file)
    normalized2 = normalizer2.normalize_path(project_file)
    print(f"Instance 1: {normalized1}")
    print(f"Instance 2: {normalized2}")
    assert normalized1 == normalized2
    print("✓ PASS")
    
    print("\n=== All Tests Passed! ===")


if __name__ == "__main__":
    try:
        test_normalizer()
    except Exception as e:
        print(f"\n✗ FAIL: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
