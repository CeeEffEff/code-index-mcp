# Product Requirements Document: Cross-File Function Call Edge Detection Fixes

**Version:** 1.0  
**Date:** January 10, 2025  
**Status:** Draft  
**Priority:** High  
**Owner:** Engineering Team

---

## 1. Executive Summary

The code indexing system currently fails to create complete cross-file function call relationships in the Neo4j graph database. This PRD addresses three critical issues that prevent accurate call graph construction:

1. **External Library Imports** - Symbol ID mismatches prevent linking calls to external dependencies
2. **Module-Level Calls** - Function calls made outside function scope are not tracked
3. **Method Call Resolution** - Insufficient context prevents matching method calls to correct classes

These gaps significantly reduce the value of the code intelligence graph, making it impossible to:
- Trace dependencies accurately across the codebase
- Identify impact of changes to external dependencies
- Understand entry points and top-level execution flow
- Perform accurate method call analysis in OOP codebases

---

## 2. Problem Statement

### 2.1 Current Behavior

The Python parsing strategy (`python_strategy.py`) attempts to link function calls across files by:
1. Detecting function calls in AST
2. Tracking import statements
3. Creating placeholder symbols for imported entities
4. Attempting to link these to actual implementations

However, three critical failure modes exist:

#### **Issue #1: External Library Import Symbol ID Mismatch**

**Symptoms:**
- Calls to functions from external libraries (e.g., `requests.get()`, `logging.info()`) create orphaned CALLS relationships
- Placeholder symbols are created but never linked to actual function definitions
- Graph contains duplicate symbols with different IDs for the same function

**Root Cause:**
```python
# python_strategy.py, lines 304-308
relative_path = os.path.relpath(import_spec.spec.origin, self.project_dir)
import_symbol_id = self._create_symbol_id(relative_path, called_function)
```

The relative path calculation fails for:
- Venv packages (e.g., `.venv/lib/python3.11/site-packages/requests/api.py`)
- System packages (e.g., `/usr/lib/python3.11/logging/__init__.py`)
- When these modules are parsed separately, they use different base paths
- Result: Symbol IDs don't match → No connection

**Example:**
```python
# file1.py
import requests
requests.get("http://example.com")  # Creates placeholder: "??/requests/api.py::get"

# If requests/api.py is indexed, it creates: "requests/api.py::get"
# These don't match → orphaned CALLS edge
```

#### **Issue #2: Module-Level Calls Not Tracked**

**Symptoms:**
- Function calls in module initialization code are not captured
- Entry point detection is incomplete
- Top-level script behavior is invisible in the graph

**Root Cause:**
```python
# python_strategy.py, lines 211-217
if not self.current_function_stack:
    logger.info(f"{called_function=} called but no function stack, trying as import call")
    self.try_as_import_call(node, called_function, None)
    return
```

When `current_function_stack` is empty (module-level code), the call is processed differently:
- `try_as_import_call` is invoked with `caller_function=None`
- The logic for handling `None` callers is ambiguous
- Import matching may fail silently
- CALLS relationships are not created properly

**Example:**
```python
# main.py (module level)
import sys
from user_management.services.user_manager import UserManager

manager = UserManager()  # This call might not be tracked
manager.create_user("Alice")  # This call might not be tracked

# Only calls inside functions are reliably tracked:
def main():
    manager = UserManager()  # This IS tracked
    manager.create_user("Alice")  # This IS tracked
```

#### **Issue #3: Method Call Resolution Insufficient Context**

**Symptoms:**
- Method calls on objects cannot be traced to specific class definitions
- Multiple classes with same method name create ambiguous matches
- `obj.method()` calls are only matched by method name, not by object type

**Root Cause:**
```python
# python_strategy.py, lines 226-236
elif isinstance(node.func, ast.Attribute):
    # Method call: obj.method() or module.function()
    called_function = node.func.attr
```

The parser only extracts the attribute name (e.g., "create_user"), losing critical context:
- No tracking of the object type that the method is called on
- Cannot distinguish `UserManager.create_user()` from `AdminManager.create_user()`
- Falls back to name matching which can produce false positives

**Example:**
```python
# Ambiguous method calls
from user_management.services.user_manager import UserManager
from admin_management.services.admin_manager import AdminManager

user_mgr = UserManager()
admin_mgr = AdminManager()

user_mgr.create_user("Alice")   # Which "create_user" is this?
admin_mgr.create_user("Bob")    # Which "create_user" is this?

# Parser only sees:
# - called_function = "create_user"
# - No type information for user_mgr or admin_mgr
# - Cannot correctly link to UserManager.create_user vs AdminManager.create_user
```

---

## 3. Goals and Success Criteria

### 3.1 Primary Goals

1. **External Library Call Linking (Issue #1)**
   - All calls to external library functions are correctly linked to their definitions
   - Symbol IDs are consistent regardless of indexing order
   - External dependencies are clearly marked in the graph

2. **Module-Level Call Tracking (Issue #2)**
   - All function/method calls in module initialization code are captured
   - Entry points are identifiable through the call graph
   - Module initialization sequence is traceable

3. **Method Call Type Resolution (Issue #3)**
   - Method calls are linked to the correct class implementation
   - Type inference tracks object types through local scope
   - Ambiguous method calls are flagged with metadata

### 3.2 Success Metrics

**Quantitative:**
- ≥95% of cross-file function calls have valid CALLS relationships
- ≥90% of module-level calls are captured in the graph
- ≥85% of method calls are linked to correct class definitions
- Zero orphaned placeholder symbols after full index build

**Qualitative:**
- Developers can trace any function call to its definition via graph queries
- Impact analysis for external dependency updates is accurate
- Code review tools can show complete call hierarchies

### 3.3 Non-Goals

- Type inference for complex polymorphism (duck typing, protocols)
- Runtime call tracking (dynamic dispatch, `getattr()`, etc.)
- Cross-language call detection (Python → C extensions)
- Call frequency or performance profiling

---

## 4. Technical Requirements

### 4.1 Symbol ID Normalization (Issue #1)

**Requirement ID:** XFCF-001  
**Priority:** P0 (Critical)

**Description:**
Implement a canonical symbol ID generation strategy that produces consistent IDs regardless of:
- Project root location
- Venv path structure
- Absolute vs relative path resolution
- Indexing order

**Technical Specification:**

```python
class SymbolIDNormalizer:
    """Centralized symbol ID generation with normalization."""
    
    def __init__(self, project_root: str, venv_root: Optional[str] = None):
        self.project_root = os.path.abspath(project_root)
        self.venv_root = os.path.abspath(venv_root) if venv_root else None
        
    def normalize_path(self, file_path: str) -> str:
        """
        Normalize a file path to canonical form.
        
        Rules:
        1. Project files: relative to project_root
        2. Venv packages: "venv://<package>/<module_path>"
        3. System packages: "stdlib://<module_path>"
        4. External paths: "external://<absolute_path>"
        """
        abs_path = os.path.abspath(file_path)
        
        # Project file
        if abs_path.startswith(self.project_root):
            return os.path.relpath(abs_path, self.project_root)
        
        # Venv package
        if self.venv_root and abs_path.startswith(self.venv_root):
            rel_to_venv = os.path.relpath(abs_path, self.venv_root)
            # Extract package name from site-packages path
            parts = Path(rel_to_venv).parts
            if "site-packages" in parts:
                idx = parts.index("site-packages")
                pkg_path = "/".join(parts[idx+1:])
                return f"venv://{pkg_path}"
        
        # Standard library (heuristic)
        if "/lib/python" in abs_path and "/site-packages" not in abs_path:
            # Extract module path after lib/pythonX.Y/
            match = re.search(r'/lib/python[\d.]+/(.+)', abs_path)
            if match:
                return f"stdlib://{match.group(1)}"
        
        # External/unknown
        return f"external://{abs_path}"
    
    def create_symbol_id(self, file_path: str, symbol_name: str) -> str:
        """Create normalized symbol ID."""
        normalized_path = self.normalize_path(file_path)
        return f"{normalized_path}::{symbol_name}"
```

**Acceptance Criteria:**
- [ ] Symbol IDs for venv packages use `venv://` prefix
- [ ] Symbol IDs for stdlib use `stdlib://` prefix
- [ ] Project files use relative paths without prefix
- [ ] Same function generates same ID across different runs
- [ ] Symbol ID resolver can map back to actual file paths

**Testing Requirements:**
- Unit tests for each path type (project, venv, stdlib, external)
- Integration test: index same project twice, verify symbol IDs match
- Edge case test: symlinks, network paths, Windows vs Unix paths

---

### 4.2 Module-Level Call Tracking (Issue #2)

**Requirement ID:** XFCF-002  
**Priority:** P0 (Critical)

**Description:**
Extend call tracking to capture function/method calls made in module initialization scope (outside any function definition).

**Technical Specification:**

```python
class SinglePassVisitor(ast.NodeVisitor):
    def __init__(self, ...):
        # Add module-level tracking
        self.module_level_calls = []  # Store module-level call info
        self.current_function_stack = []  # Empty = module level
        
    def visit_Call(self, node: ast.Call):
        """Visit function call and record relationship."""
        called_function = self._extract_called_function(node)
        
        if self.current_function_stack:
            # Function-level call (existing logic)
            caller_function = self.current_function_stack[-1]
            self._record_call(caller_function, called_function, node)
        else:
            # Module-level call (NEW)
            module_id = f"{self.file_path}::<module>"
            self._record_call(module_id, called_function, node)
            self.module_level_calls.append({
                "caller": module_id,
                "called": called_function,
                "line": node.lineno
            })
```

**Graph Schema Changes:**
```cypher
// Add special <module> symbol for each file
(:File {path: "main.py"})-[:CONTAINS]->(:Symbol {
    qualified_name: "main.py::<module>",
    type: "module_init",
    name: "<module>"
})

// Module-level calls link from <module> symbol
(:Symbol {qualified_name: "main.py::<module>"})-[:CALLS]->
(:Symbol {qualified_name: "user_management/services/user_manager.py::UserManager"})
```

**Acceptance Criteria:**
- [ ] Each file has a `<module>` symbol representing module initialization
- [ ] All module-level function calls create CALLS edges from `<module>` symbol
- [ ] Module-level import side effects are captured
- [ ] Entry point detection works via `<module>` symbol analysis

**Testing Requirements:**
- Test file with only module-level calls (no functions)
- Test mixed module-level and function-level calls
- Test module importing another module (transitive initialization)
- Test script execution entry points

---

### 4.3 Method Call Type Resolution (Issue #3)

**Requirement ID:** XFCF-003  
**Priority:** P1 (High)

**Description:**
Implement local type inference to track object types and resolve method calls to the correct class definition.

**Technical Specification:**

```python
class TypeInferenceVisitor(ast.NodeVisitor):
    """Track variable type assignments within function scope."""
    
    def __init__(self):
        self.type_map = {}  # variable_name -> type_info
        
    def visit_Assign(self, node: ast.Assign):
        """Track assignments to infer types."""
        # x = ClassName()
        if isinstance(node.value, ast.Call):
            if isinstance(node.value.func, ast.Name):
                class_name = node.value.func.id
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.type_map[target.id] = {
                            "type": "instance",
                            "class": class_name,
                            "line": node.lineno
                        }
                        
        # from module import Class; x = Class()
        # Handle various assignment patterns
        
    def infer_type(self, node: ast.AST) -> Optional[str]:
        """Infer the type of an expression."""
        if isinstance(node, ast.Name):
            return self.type_map.get(node.id, {}).get("class")
        # Add more inference rules...
        return None

class SinglePassVisitor(ast.NodeVisitor):
    def __init__(self, ...):
        self.type_tracker = TypeInferenceVisitor()
        
    def visit_Call(self, node: ast.Call):
        """Enhanced call resolution with type inference."""
        if isinstance(node.func, ast.Attribute):
            # obj.method()
            method_name = node.func.attr
            obj_type = self.type_tracker.infer_type(node.func.value)
            
            if obj_type:
                # Fully qualified method lookup
                qualified_method = f"{obj_type}.{method_name}"
                self._record_typed_call(qualified_method, node)
            else:
                # Fallback: untyped method call
                self._record_untyped_call(method_name, node)
```

**Graph Metadata:**
```cypher
// Typed method calls
(:Symbol {qualified_name: "main.py::main"})-[:CALLS {
    type: "method",
    confidence: "high",
    inferred_class: "UserManager"
}]->(:Symbol {qualified_name: "services/user_manager.py::UserManager.create_user"})

// Untyped method calls (ambiguous)
(:Symbol {qualified_name: "main.py::main"})-[:CALLS {
    type: "method",
    confidence: "low",
    method_name: "create_user"
}]->(:Symbol {qualified_name: "services/user_manager.py::UserManager.create_user"})
```

**Acceptance Criteria:**
- [ ] Local variable assignments track type information
- [ ] Method calls on typed objects resolve to correct class
- [ ] Ambiguous method calls are flagged with `confidence: "low"`
- [ ] Import-based type resolution works (import Class; x = Class())
- [ ] Type information propagates through local scope

**Testing Requirements:**
- Test simple instance creation and method call
- Test method chaining (obj.method1().method2())
- Test ambiguous calls with multiple classes having same method
- Test imported class instantiation

---

## 5. Implementation Plan

### 5.1 Phase 1: Symbol ID Normalization (Week 1-2)

**Tasks:**
1. Implement `SymbolIDNormalizer` class
2. Refactor `python_strategy.py` to use normalizer
3. Update `neo4j_index_builder.py` to pass normalizer to strategies
4. Add path resolution unit tests
5. Add integration test for symbol ID consistency

**Dependencies:** None

**Deliverables:**
- `symbol_id_normalizer.py` module
- Updated parsing strategy
- Test suite with ≥90% coverage

### 5.2 Phase 2: Module-Level Call Tracking (Week 2-3)

**Tasks:**
1. Add `<module>` symbol creation in `SinglePassVisitor`
2. Extend `visit_Call` to handle empty function stack
3. Update Neo4j schema to support module symbols
4. Create Cypher queries for entry point detection
5. Add module-level call tests

**Dependencies:** Phase 1 (symbol ID changes)

**Deliverables:**
- Enhanced `SinglePassVisitor` with module tracking
- Neo4j schema migration
- Entry point detection queries

### 5.3 Phase 3: Type Inference for Method Calls (Week 3-5)

**Tasks:**
1. Implement `TypeInferenceVisitor` for local scope
2. Integrate type inference into `SinglePassVisitor`
3. Add type confidence metadata to CALLS relationships
4. Create type resolution tests
5. Add ambiguity detection and reporting

**Dependencies:** Phase 1 (symbol ID changes)

**Deliverables:**
- `TypeInferenceVisitor` class
- Enhanced call resolution with types
- Ambiguity detection tooling

### 5.4 Phase 4: Validation and Testing (Week 5-6)

**Tasks:**
1. Run full index on production codebase
2. Compare before/after call graph completeness
3. Create validation queries for edge detection
4. Performance testing and optimization
5. Documentation updates

**Dependencies:** Phases 1-3 complete

**Deliverables:**
- Validation report with metrics
- Performance benchmarks
- Updated documentation

---

## 6. Testing Strategy

### 6.1 Unit Tests

**Coverage Requirements:** ≥90% for new code

**Test Categories:**
1. Symbol ID normalization (all path types)
2. Module-level call detection
3. Type inference rules
4. Edge cases and error handling

### 6.2 Integration Tests

**Test Scenarios:**
1. Index sample project, verify cross-file CALLS count
2. Index with external dependencies (requests, flask)
3. Compare graph before/after fixes
4. Performance test: index large codebase (>10k files)

### 6.3 Validation Queries

**Neo4j Validation Queries:**

```cypher
// Q1: Count cross-file calls
MATCH (caller_file:File)-[:CONTAINS]->(caller:Symbol)-[:CALLS]->(called:Symbol)<-[:CONTAINS]-(called_file:File)
WHERE caller_file.path <> called_file.path
RETURN count(*) as cross_file_calls

// Q2: Find orphaned placeholder symbols
MATCH (s:Symbol)
WHERE s.line = -1 AND NOT ()-[:CALLS]->(s)
RETURN s.qualified_name, s.type

// Q3: Find module-level entry points
MATCH (f:File)-[:CONTAINS]->(m:Symbol {type: "module_init"})-[:CALLS]->(called:Symbol)
RETURN f.path, collect(called.qualified_name) as entry_calls

// Q4: Find ambiguous method calls
MATCH ()-[r:CALLS {confidence: "low"}]->()
RETURN count(*) as ambiguous_calls, collect(r) as examples LIMIT 10
```

---

## 7. Risks and Mitigation

### 7.1 Technical Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Type inference limited by Python's dynamic nature | High | High | Accept limitation, flag ambiguous cases, improve over time |
| Performance degradation with type tracking | Medium | Medium | Profile and optimize, consider lazy evaluation |
| Breaking changes to existing graph schema | High | Low | Implement backward compatibility, provide migration script |
| External library symbols too numerous | Medium | Medium | Add configurable filtering, limit depth |

### 7.2 Schedule Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Type inference more complex than estimated | High | Phase 3 is P1 (not P0), can be deferred if needed |
| Integration testing reveals unforeseen issues | Medium | Build in 1-week buffer before release |

---

## 8. Success Validation

### 8.1 Acceptance Testing

**Test Project:** Use `test/sample-projects/python/user-management`

**Before Fix:**
```cypher
// Expected: ~0-5 cross-file calls detected
MATCH (caller_file:File)-[:CONTAINS]->(caller:Symbol)-[:CALLS]->(called:Symbol)<-[:CONTAINS]-(called_file:File)
WHERE caller_file.path <> called_file.path
RETURN count(*) as cross_file_calls
```

**After Fix (Target):**
```cypher
// Expected: ≥20 cross-file calls detected
MATCH (caller_file:File)-[:CONTAINS]->(caller:Symbol)-[:CALLS]->(called:Symbol)<-[:CONTAINS]-(called_file:File)
WHERE caller_file.path <> called_file.path
RETURN count(*) as cross_file_calls
```

### 8.2 Release Criteria

**Blocker (Must Fix):**
- [ ] Symbol ID consistency test passes
- [ ] Module-level calls captured for test project
- [ ] Zero orphaned symbols after full index
- [ ] No regressions in existing call detection

**Important (Should Fix):**
- [ ] Method call type resolution ≥85% accuracy
- [ ] Performance within 20% of baseline
- [ ] All unit tests pass
- [ ] Integration tests pass

**Nice to Have:**
- [ ] Documentation with examples
- [ ] Debugging queries documented
- [ ] Performance profiling report

---

## 9. Future Enhancements

**Post-V1 Improvements:**

1. **Advanced Type Inference**
   - Inter-procedural type flow
   - Return type inference
   - Generic type tracking

2. **Dynamic Call Detection**
   - `getattr()` call tracking
   - `exec()` / `eval()` analysis
   - Decorator call tracking

3. **Cross-Language Support**
   - Python → C extension calls
   - Python → JavaScript (via bridges)

4. **Runtime Validation**
   - Compare static call graph to runtime traces
   - Identify missing edges via instrumentation

---

## 10. Appendix

### 10.1 Related Documents

- [ARCHITECTURE.md](../../../ARCHITECTURE.md) - System architecture
- [CROSS_FILE_CALLS_FIX.md](./CROSS_FILE_CALLS_FIX.md) - Technical investigation
- [python_strategy.py](../strategies/python_strategy.py) - Current implementation

### 10.2 References

- Python AST documentation: https://docs.python.org/3/library/ast.html
- Neo4j Cypher manual: https://neo4j.com/docs/cypher-manual/current/
- Type inference resources: https://en.wikipedia.org/wiki/Type_inference

### 10.3 Glossary

- **Symbol ID**: Unique identifier for code symbols (format: `<path>::<name>`)
- **Cross-file call**: Function/method call where caller and callee are in different files
- **Module-level call**: Function call in module initialization scope (not in any function)
- **Type inference**: Static analysis to determine variable types without runtime info
- **Call graph**: Directed graph showing which functions call which other functions
