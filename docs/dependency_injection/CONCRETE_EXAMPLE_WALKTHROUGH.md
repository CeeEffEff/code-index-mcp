# Concrete Example: Step-by-Step Detection

## The Exact Code Being Analyzed

```python
# ═══════════════════════════════════════════════════════════════════════
# FILE: src/ai_service.py
# ═══════════════════════════════════════════════════════════════════════

from gemini_client import GeminiLlmClient
from job import Job

class AIService:
    """Main AI service that processes jobs using an LLM client."""

    def __init__(self, llm_client: GeminiLlmClient):
        """
        Initialize the service.

        Args:
            llm_client: The LLM client to use for processing
        """
        self.client = llm_client
        self.job_count = 0

    def process_job(self, job: Job) -> dict:
        """Process a job using the LLM client."""
        self.job_count += 1

        # THIS IS THE KEY LINE - Call through DI'd attribute
        response = self.client.send_job(job)

        return response


# ═══════════════════════════════════════════════════════════════════════
# FILE: src/gemini_client.py
# ═══════════════════════════════════════════════════════════════════════

class GeminiLlmClient:
    """Client for Google's Gemini LLM API."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def send_job(self, job) -> dict:
        """Send a job to the Gemini API."""
        # LLM API call logic here
        return {"status": "success", "result": "..."}
```

---

## Detection Flow: Frame by Frame

### Frame 1: Parser Enters `__init__` Method

```python
def __init__(self, llm_client: GeminiLlmClient):
    #              └────────┬────────────────┘
    #                       │
    #       Parser sees: "Parameter with type annotation"
```

**What the parser does:**

```python
# In visit_FunctionDef() method:
function_id = "src/ai_service.py::AIService.__init__"
self._extract_parameter_types(node, function_id)

# Result stored in memory:
self.parameter_types[
    ("src/ai_service.py::AIService.__init__", "llm_client")
] = "GeminiLlmClient"
```

**Memory state after this:**

```python
{
    "parameter_types": {
        ("src/ai_service.py::AIService.__init__", "llm_client"): "GeminiLlmClient"
    }
}
```

---

### Frame 2: Parser Sees Assignment

```python
self.client = llm_client
#    └─┬─┘   └────┬────┘
#      │          │
#   attribute  parameter
```

**What the parser does:**

```python
# In visit_Assign() method:
target = "client"  # self.client
value = {"type": "variable", "name": "llm_client"}

# Result stored in memory:
self.attribute_assignments[
    ("AIService", "client")
] = {"type": "variable", "name": "llm_client"}
```

**Memory state now:**

```python
{
    "parameter_types": {
        ("src/ai_service.py::AIService.__init__", "llm_client"): "GeminiLlmClient"
    },
    "attribute_assignments": {
        ("AIService", "client"): {"type": "variable", "name": "llm_client"}
    }
}
```

---

### Frame 3: Parser Enters `process_job` Method

```python
def process_job(self, job: Job) -> dict:
    response = self.client.send_job(job)
    #               └──┬──┘ └───┬───┘
    #                  │        │
    #              attribute  method
```

**What the parser does (Step 1 - Detect call):**

```python
# In visit_Call() method:
called_method = "send_job"  # The method being called

# Check if calling through an attribute
obj_node = node.func.value  # This is "self.client"
obj_info = self._resolve_object_reference(obj_node)
```

**What `_resolve_object_reference` does:**

```python
# obj_node is: self.client
# It's an Attribute node with:
#   - value = "self"
#   - attr = "client"

# Look up in memory:
current_class = "AIService"
attr_name = "client"
key = ("AIService", "client")

# Found in attribute_assignments!
obj_info = {
    "type": "variable",
    "name": "llm_client"
}
```

**Memory state (unchanged, but we found a match!):**

```python
Found: attribute_assignments[("AIService", "client")] =
    {"type": "variable", "name": "llm_client"}
```

---

### Frame 4: Create Inferred Call

**What the parser does (Step 2 - Resolve type):**

```python
# In _create_inferred_call():
obj_info = {"type": "variable", "name": "llm_client"}
method_name = "send_job"

# Since obj_info["type"] == "variable", look up the parameter type:
param_name = "llm_client"

# Search parameter_types for this parameter
for (func_id, param), type_name in self.parameter_types.items():
    if param == "llm_client":
        # FOUND!
        type_name = "GeminiLlmClient"
        break

# Now we know:
# - self.client comes from parameter llm_client
# - llm_client has type GeminiLlmClient
# - Therefore, self.client is a GeminiLlmClient
# - Therefore, send_job is GeminiLlmClient.send_job
```

**What the parser does (Step 3 - Create relationship):**

```python
# Construct the full method reference:
full_method_ref = "GeminiLlmClient.send_job"

# Check if this is an import (cross-file)
self.try_as_import_call(None, full_method_ref, caller_function)

# This creates an ImportCallInfo:
import_call_info = ImportCallInfo(
    called_symbol_id="src/gemini_client.py::GeminiLlmClient.send_job",
    called_symbol_info=SymbolInfo(
        type="method",
        file="src/gemini_client.py",
        called_by=["src/ai_service.py::AIService.process_job"]
    )
)
```

---

### Frame 5: Store in Neo4j

**What neo4j_index_builder.py does:**

```python
# In _add_symbol_to_neo4j():
for caller_id in symbol_info.called_by:
    # caller_id = "src/ai_service.py::AIService.process_job"
    # symbol_id = "src/gemini_client.py::GeminiLlmClient.send_job"

    # Determine if cross-file
    caller_file = "src/ai_service.py"
    called_file = "src/gemini_client.py"
    is_cross_file = True  # Different files!

    # Create relationship in Neo4j
    session.run("""
        MATCH (called:Symbol {qualified_name: $called_id})
        MERGE (caller:Symbol {qualified_name: $caller_id})
        MERGE (caller)-[r:CALLS]->(called)
        SET r.cross_file = $is_cross_file,
            r.source = 'ast_analysis'
    """, {
        "called_id": "src/gemini_client.py::GeminiLlmClient.send_job",
        "caller_id": "src/ai_service.py::AIService.process_job",
        "is_cross_file": True
    })
```

---

## Final Neo4j Graph

```cypher
// The nodes
(:Symbol {
    qualified_name: "src/ai_service.py::AIService.process_job",
    name: "process_job",
    type: "method",
    file: "src/ai_service.py",
    line: 18
})

(:Symbol {
    qualified_name: "src/gemini_client.py::GeminiLlmClient.send_job",
    name: "send_job",
    type: "method",
    file: "src/gemini_client.py",
    line: 12
})

// The relationship (THE KEY PART!)
(:Symbol {qualified_name: "src/ai_service.py::AIService.process_job"})
    -[:CALLS {
        cross_file: true,
        source: "ast_analysis"
    }]->
(:Symbol {qualified_name: "src/gemini_client.py::GeminiLlmClient.send_job"})
```

---

## Query to Find This Relationship

```cypher
MATCH (ai:Symbol)-[r:CALLS]->(gem:Symbol)
WHERE ai.qualified_name CONTAINS "AIService.process_job"
  AND gem.qualified_name CONTAINS "send_job"
RETURN
    ai.qualified_name AS caller,
    r.cross_file AS crosses_files,
    r.source AS detection_method,
    gem.qualified_name AS called
```

**Expected output:**

```
caller                                    | crosses_files | detection_method | called
------------------------------------------|---------------|------------------|----------------------------------
src/ai_service.py::AIService.process_job  | true          | ast_analysis     | src/gemini_client.py::GeminiLlmClient.send_job
```

---

## Side-by-Side Comparison

### OLD PARSER (Before Changes)

```
Step 1: Parse __init__
  ✓ Creates node: AIService.__init__
  ✗ IGNORES type hint GeminiLlmClient
  ✗ IGNORES assignment self.client = llm_client

Step 2: Parse process_job
  ✓ Creates node: AIService.process_job
  ✗ Sees self.client.send_job() but can't resolve it
  ✗ NO RELATIONSHIP CREATED

Result: INCOMPLETE GRAPH
```

### NEW PARSER (After Changes)

```
Step 1: Parse __init__
  ✓ Creates node: AIService.__init__
  ✓ STORES type hint: llm_client → GeminiLlmClient
  ✓ TRACKS assignment: self.client → llm_client

Step 2: Parse process_job
  ✓ Creates node: AIService.process_job
  ✓ Sees self.client.send_job()
  ✓ RESOLVES: self.client → llm_client → GeminiLlmClient
  ✓ CREATES RELATIONSHIP:
      AIService.process_job → GeminiLlmClient.send_job

Result: COMPLETE GRAPH ✓
```

---

## Memory Trace Table

| Line Parsed | Memory Structure Updated | Value Stored |
|-------------|--------------------------|--------------|
| `def __init__(self, llm_client: GeminiLlmClient):` | `parameter_types` | `{("AIService.__init__", "llm_client"): "GeminiLlmClient"}` |
| `self.client = llm_client` | `attribute_assignments` | `{("AIService", "client"): {"type": "variable", "name": "llm_client"}}` |
| `self.client.send_job(job)` | **Uses both lookups above** | **Creates relationship in graph** |

---

## Why This Matters: Real Impact

### Question: "What does AIService.process_job call?"

**OLD GRAPH:**

```cypher
MATCH (s:Symbol {qualified_name: "...AIService.process_job"})-[:CALLS]->(t)
RETURN t.name

// Result: (empty)
// Answer: "I don't know 🤷"
```

**NEW GRAPH:**

```cypher
MATCH (s:Symbol {qualified_name: "...AIService.process_job"})-[:CALLS]->(t)
RETURN t.qualified_name

// Result:
// "src/gemini_client.py::GeminiLlmClient.send_job"
// Answer: "It calls GeminiLlmClient.send_job ✓"
```

---

## The Three-Step Magic Formula

```
1. TYPE HINT   def __init__(self, param: Type):
   └─> Remember: param is of Type

2. ASSIGNMENT  self.attr = param
   └─> Remember: attr comes from param

3. CALL        self.attr.method()
   └─> Resolve: attr → param → Type → Type.method()
   └─> CREATE: current_function → Type.method ✓
```

This is how we bridge the gap from **indirect reference** to **actual implementation**.

---

## Verification Script

Save this as `verify_detection.py`:

```python
from neo4j import GraphDatabase

def verify():
    driver = GraphDatabase.driver("bolt://localhost:7687",
                                   auth=("neo4j", "password"))

    with driver.session() as session:
        # Check if our specific example was captured
        result = session.run("""
            MATCH (ai)-[r:CALLS]->(gem)
            WHERE ai.qualified_name CONTAINS 'AIService.process_job'
              AND gem.qualified_name CONTAINS 'send_job'
            RETURN count(*) as found
        """)

        count = result.single()["found"]

        if count > 0:
            print("✅ SUCCESS! DI relationship detected!")
            print(f"   Found {count} relationship(s)")
        else:
            print("❌ FAILED: No relationship found")
            print("   The detection might not be working")

    driver.close()

if __name__ == "__main__":
    verify()
```

Run it:

```bash
python verify_detection.py
```

Expected output:

```
✅ SUCCESS! DI relationship detected!
   Found 1 relationship(s)
```

---

## Summary: The Complete Journey

```
┌─────────────────────────────────────────────────────────────┐
│ SOURCE CODE                                                 │
│                                                             │
│ def __init__(self, llm_client: GeminiLlmClient):          │
│     self.client = llm_client                               │
│                                                             │
│ def process_job(self, job):                               │
│     return self.client.send_job(job)                       │
└─────────────────────────────────────────────────────────────┘
                         ▼ PARSE
┌─────────────────────────────────────────────────────────────┐
│ MEMORY (During Parsing)                                     │
│                                                             │
│ parameter_types: {                                          │
│   ("__init__", "llm_client"): "GeminiLlmClient"           │
│ }                                                           │
│                                                             │
│ attribute_assignments: {                                    │
│   ("AIService", "client"): {"name": "llm_client"}         │
│ }                                                           │
└─────────────────────────────────────────────────────────────┘
                         ▼ RESOLVE
┌─────────────────────────────────────────────────────────────┐
│ INFERENCE                                                   │
│                                                             │
│ self.client → llm_client → GeminiLlmClient                 │
│                                                             │
│ Therefore:                                                  │
│ self.client.send_job() = GeminiLlmClient.send_job()       │
└─────────────────────────────────────────────────────────────┘
                         ▼ STORE
┌─────────────────────────────────────────────────────────────┐
│ NEO4J GRAPH                                                 │
│                                                             │
│ (AIService.process_job)                                    │
│         │                                                   │
│         └──[:CALLS {cross_file: true}]──>                  │
│                                                             │
│ (GeminiLlmClient.send_job)                                 │
│                                                             │
│ ✅ RELATIONSHIP CAPTURED!                                   │
└─────────────────────────────────────────────────────────────┘
```

**That's the complete story of how one line of code:**

```python
return self.client.send_job(job)
```

**Becomes a relationship in the graph:**

```
AIService.process_job → GeminiLlmClient.send_job
```
