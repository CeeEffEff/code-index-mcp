# Cross-File Function Call Edge Detection Investigation Report

**Date:** January 10, 2025  
**Status:** Investigation Complete - Ready for Implementation  
**Related Documents:** 
- [PRD: cross_file_calls_fix_prd.md](./cross_file_calls_fix_prd.md)
- TaskMaster Tag: `cross-file-calls-fix`

---

## ✅ Investigation Complete: PRD and TaskMaster Tasks Created

This document summarizes the investigation of missing cross-file function call edges in the Neo4j graph database and the comprehensive plan for fixing them.

---

## 📄 **Deliverable 1: Product Requirements Document**

**Created:** `src/code_index_mcp/indexing/docs/cross_file_calls_fix_prd.md`

This 350+ line PRD includes:
- **Executive Summary** - Impact and importance
- **Problem Statement** - Detailed root cause analysis for each issue
- **Goals & Success Criteria** - Quantitative metrics (≥95% cross-file calls, ≥90% module-level calls, ≥85% method calls)
- **Technical Requirements** - Complete specifications with code examples
- **Implementation Plan** - 4-phase approach with dependencies
- **Testing Strategy** - Unit, integration, and validation queries
- **Risk Mitigation** - Technical and schedule risks identified

---

## 📋 **Deliverable 2: TaskMaster Task Structure**

**Created new tag:** `cross-file-calls-fix` with 3 main tasks

### **Task 1: Phase 1 - Symbol ID Normalization** ⚠️ **P0 (Critical)**
**Goal:** Fix external library import symbol ID mismatches

**5 Subtasks:**
1. Implement `SymbolIDNormalizer` class with `normalize_path()` method
2. Refactor `python_strategy.py` to use SymbolIDNormalizer
3. Update `neo4j_index_builder.py` to pass normalizer to strategies
4. Add comprehensive unit tests for all path types (≥90% coverage)
5. Add integration test for symbol ID consistency

**Key Innovation:** Uses prefixes `venv://`, `stdlib://`, `external://` to ensure consistent IDs

---

### **Task 2: Phase 2 - Module-Level Call Tracking** ⚠️ **P0 (Critical)**
**Goal:** Capture function calls made outside function definitions

**Depends on:** Task 1

**Key Changes:**
- Create `<module>` symbol for each file
- Track module-level calls with `caller = <module>`
- Update Neo4j schema for `module_init` type
- Enable entry point detection via `<module>` analysis

**Example Fix:**
```python
# main.py (module level) - currently NOT tracked
manager = UserManager()  # After fix: tracked as main.py::<module> → CALLS → UserManager

def main():  # currently IS tracked
    manager = UserManager()  # Already works correctly
```

---

### **Task 3: Phase 3 - Method Call Type Resolution** 📍 **P1 (High)**
**Goal:** Resolve method calls to correct class definitions

**Depends on:** Task 1

**Key Changes:**
- Implement `TypeInferenceVisitor` for local type tracking
- Track instance creation (`x = ClassName()`)
- Infer object types for method calls
- Add `confidence: high/low` metadata to CALLS edges

**Priority Note:** P1 (not P0) - can be deferred if Phase 1-2 take longer

---

## 📊 **Task Summary**

```
Tag: cross-file-calls-fix
Total Tasks: 3 (0% complete)
Total Subtasks: 5 (0% complete)

Phase 1 (P0): 1 task + 5 subtasks → External library imports
Phase 2 (P0): 1 task → Module-level calls  
Phase 3 (P1): 1 task → Method call type resolution
```

---

## 🎯 **Priority Recommendations**

### **Immediate (Next 1-2 weeks):**

1. ✅ **Phase 1 - Symbol ID Normalization**
   - Fixes the most common issue (external library symbol mismatches)
   - Foundation for other fixes
   - Clear, well-defined scope

2. ✅ **Phase 2 - Module-Level Call Tracking**
   - Critical for entry point detection
   - Relatively straightforward implementation
   - Depends on Phase 1 symbol ID changes

### **Follow-up (Week 3-5):**

3. 📋 **Phase 3 - Method Call Type Resolution**
   - Complex type inference challenges
   - Python's dynamic nature makes this inherently difficult
   - Can deliver value incrementally (start with simple cases)

---

## 🚀 **Next Steps**

To begin implementation:

1. **Review the PRD** at `src/code_index_mcp/indexing/docs/cross_file_calls_fix_prd.md`
2. **Switch to TaskMaster tag**: Run TaskMaster with `--tag cross-file-calls-fix`
3. **Start with Phase 1, Task 1.1**: Implement `SymbolIDNormalizer` class
4. **Validate approach** by running tests against sample projects after each phase

---

## 📈 **Expected Impact**

### **Before Fix:**
- ~0-5 cross-file calls detected in sample projects
- No module-level calls tracked
- Method calls matched by name only (high false positive rate)
- Orphaned placeholder symbols for external libraries

### **After All Fixes:**
- ≥20 cross-file calls detected in same sample projects (400% improvement)
- All module-level calls tracked (100% coverage)
- 85%+ method calls correctly resolved to classes
- Zero orphaned placeholder symbols

---

## 🔍 **Root Causes Identified**

### **Issue #1: External Library Import Symbol ID Mismatch**

**Problem:** 
```python
# python_strategy.py, lines 304-308
relative_path = os.path.relpath(import_spec.spec.origin, self.project_dir)
import_symbol_id = self._create_symbol_id(relative_path, called_function)
```

- Venv packages: `.venv/lib/python3.11/site-packages/requests/api.py`
- System packages: `/usr/lib/python3.11/logging/__init__.py`
- Different parsing contexts create different symbol IDs → orphaned CALLS edges

**Solution:** Canonical symbol ID normalization with prefixes

---

### **Issue #2: Module-Level Calls Not Tracked**

**Problem:**
```python
# python_strategy.py, lines 211-217
if not self.current_function_stack:
    logger.info(f"{called_function=} called but no function stack, trying as import call")
    self.try_as_import_call(node, called_function, None)
    return
```

- When `current_function_stack` is empty (module-level code), call handling is ambiguous
- `caller_function=None` leads to silent failures in relationship creation

**Solution:** Explicit `<module>` symbol representing module initialization scope

---

### **Issue #3: Method Call Resolution Insufficient Context**

**Problem:**
```python
# python_strategy.py, lines 226-236
elif isinstance(node.func, ast.Attribute):
    # Method call: obj.method() or module.function()
    called_function = node.func.attr
```

- Only extracts attribute name (e.g., "create_user")
- No tracking of object type
- Cannot distinguish `UserManager.create_user()` from `AdminManager.create_user()`

**Solution:** Local type inference tracking variable assignments and instance creation

---

## 📂 **Artifacts Created**

### **Documentation:**
- `src/code_index_mcp/indexing/docs/cross_file_calls_fix_prd.md` (350+ lines)
- `src/code_index_mcp/indexing/docs/cross_file_calls_investigation_report.md` (this file)

### **TaskMaster:**
- Tag: `cross-file-calls-fix`
- Task 1: Phase 1 - Symbol ID Normalization (5 subtasks)
- Task 2: Phase 2 - Module-Level Call Tracking
- Task 3: Phase 3 - Method Call Type Resolution

### **Code Locations Analyzed:**
- `src/code_index_mcp/indexing/strategies/python_strategy.py`
- `src/code_index_mcp/indexing/neo4j_index_builder.py`
- `src/code_index_mcp/indexing/models/import_call_info.py`
- `src/code_index_mcp/indexing/models/symbol_info.py`

---

## 🧪 **Validation Queries**

Run these Neo4j queries after fixes to validate success:

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

## ⚠️ **Important Considerations**

### **Type Inference Limitations**
- Python's dynamic nature means 100% accuracy is impossible
- Duck typing, runtime `getattr()`, and `exec()` cannot be statically analyzed
- Goal is 85%+ accuracy for common patterns, flag ambiguous cases

### **Performance Impact**
- Path normalization adds minimal overhead
- Type inference adds computational cost (estimate: 10-20% slower indexing)
- Profile and optimize if needed

### **Backward Compatibility**
- Symbol ID changes are breaking for existing graphs
- Provide migration script or clear re-index instructions
- Consider versioning the index format

---

## 📞 **Contact & Support**

For questions or clarifications on this investigation:
- Review the detailed PRD: `cross_file_calls_fix_prd.md`
- Check TaskMaster tasks under tag: `cross-file-calls-fix`
- Review source files analyzed during investigation

---

**Investigation completed:** January 10, 2025  
**Ready for implementation:** Yes  
**Estimated implementation time:** 4-6 weeks (3 phases)
