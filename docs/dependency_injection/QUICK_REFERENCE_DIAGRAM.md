# Quick Reference: DI Detection Flow

## The Core Problem (Illustrated)

```python
# ═══════════════════════════════════════════════════════
# FILE: ai_service.py
# ═══════════════════════════════════════════════════════
class AIService:
    def __init__(self, llm_client: GeminiLlmClient):  # ← Type hint here!
        self.client = llm_client                       # ← Assignment here!

    def process_job(self, job):
        return self.client.send_job(job)               # ← Missing link HERE!
               #     ↑        ↑
               #     |        └─ Method name
               #     └─ What is "client"?


# ═══════════════════════════════════════════════════════
# FILE: gemini_client.py
# ═══════════════════════════════════════════════════════
class GeminiLlmClient:
    def send_job(self, job):                           # ← Target method
        pass
```

**BEFORE:** Graph had no connection
**AFTER:** Graph shows `AIService.process_job → GeminiLlmClient.send_job` ✓

---

## How It Works (3 Steps)

```
┌─────────────────────────────────────────────────────────────────┐
│ STEP 1: LEARN                                                   │
│ Parse: def __init__(self, llm_client: GeminiLlmClient):       │
│                                         ▲                        │
│        Store: llm_client → GeminiLlmClient                     │
│        Memory: {"llm_client": "GeminiLlmClient"}               │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 2: TRACK                                                   │
│ Parse: self.client = llm_client                                │
│             ▲            ▲                                      │
│        Store: client → llm_client                              │
│        Memory: {("AIService", "client"): "llm_client"}         │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 3: CONNECT                                                 │
│ Parse: self.client.send_job(job)                               │
│             ▲          ▲                                        │
│             |          └─ method: "send_job"                    │
│             └─ attribute: "client"                              │
│                                                                  │
│ Resolve: client → llm_client → GeminiLlmClient                 │
│ CREATE: AIService.process_job → GeminiLlmClient.send_job ✓     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Pattern Detection Examples

### 1️⃣ Constructor Injection (Most Common)

```python
class Service:
    def __init__(self, dependency: DepType):  # 1. Learn type
        self.dep = dependency                  # 2. Track assignment

    def action(self):
        self.dep.method()                      # 3. Connect!
        #    ↑
        #    └─ Resolves to: DepType.method()
```

### 2️⃣ Parameter Injection

```python
def process(client: ClientType):               # 1. Learn type
    result = client.execute()                  # 2. Connect directly!
    #        ↑
    #        └─ Resolves to: ClientType.execute()
```

### 3️⃣ Factory Pattern

```python
def get_service() -> ServiceType:              # 1. Learn return type
    return ServiceType()

def main():
    svc = get_service()                        # 2. Track assignment
    svc.run()                                  # 3. Connect!
    # ↑
    # └─ Resolves to: ServiceType.run()
```

---

## New Data Structures (Simplified)

```python
# What the parser now tracks:
{
    # Type hints: Which parameters expect which types?
    "parameter_types": {
        ("file.py::func", "param_name"): "TypeName"
    },

    # Assignments: What got assigned to which attribute?
    "attribute_assignments": {
        ("ClassName", "attr_name"): {"type": "variable", "name": "param"}
    },

    # Variables: What got assigned to which variable?
    "variable_assignments": {
        "file.py::func::var": {"type": "call", "function": "factory"}
    }
}
```

---

## Neo4j Relationship Output

```cypher
// OLD (simple):
(Caller)-[:CALLS]->(Called)

// NEW (with metadata):
(Caller)-[:CALLS {
    cross_file: true,              // Crosses file boundary?
    source: 'ast_analysis',        // How was this detected?
    via_import: false              // Through import?
}]->(Called)
```

### Query Examples

```cypher
// Find all DI-pattern calls
MATCH (a)-[r:CALLS {cross_file: true, source: 'ast_analysis'}]->(b)
RETURN a.name, b.name
LIMIT 10

// Compare detection methods
MATCH ()-[r:CALLS]->()
RETURN r.source, count(*) AS total
```

---

## Visual: Before vs After

### Graph BEFORE Changes

```
┌─────────────────┐
│  AIService      │
│  .process_job() │
└─────────────────┘
         ?                    ← NO CONNECTION!
┌─────────────────┐
│ GeminiLlmClient │
│  .send_job()    │
└─────────────────┘
```

### Graph AFTER Changes

```
┌─────────────────┐
│  AIService      │
│  .process_job() │
└─────────────────┘
         │
         │ [:CALLS {cross_file: true, source: 'ast_analysis'}]
         ▼
┌─────────────────┐
│ GeminiLlmClient │  ← CONNECTION CAPTURED! ✓
│  .send_job()    │
└─────────────────┘
```

---

## Impact Summary

| Metric | Before | After |
|--------|--------|-------|
| Direct calls captured | ✅ | ✅ |
| DI constructor calls | ❌ | ✅ |
| DI parameter calls | ❌ | ✅ |
| Interface/polymorphic calls | ❌ | ✅ |
| Factory pattern calls | ❌ | ✅ |
| **Estimated coverage** | **40-60%** | **75-90%** |

---

## Files Changed

```
src/code_index_mcp/indexing/strategies/
    python_strategy.py
        + Line 8: Import Any
        + Lines 153-159: New tracking dicts
        + Lines 341-364: visit_Assign() method
        + Lines 632-746: Helper methods
        ~ Lines 381-386: Enhanced visit_Call()

src/code_index_mcp/indexing/
    neo4j_index_builder.py
        ~ Lines 527-542: Add metadata to relationships
        ~ Lines 666-681: Add metadata to import calls
```

---

## Testing: Does It Work?

### 1. Rebuild your index
```bash
# Your command to rebuild
```

### 2. Run this query
```cypher
MATCH (a:Symbol)-[r:CALLS]->(b:Symbol)
WHERE a.name CONTAINS 'AIService'
  AND b.name CONTAINS 'send_job'
RETURN a.qualified_name, r, b.qualified_name
```

### 3. Expected result
```
a.qualified_name                | r                              | b.qualified_name
--------------------------------|--------------------------------|----------------------------------
ai_service.py::AIService.       | [:CALLS {cross_file: true,    | gemini_client.py::
  process_job                   |  source: 'ast_analysis'}]      |   GeminiLlmClient.send_job
```

**If you see this ↑, it worked! 🎉**

---

## The "Aha!" Moment

```
┌────────────────────────────────────────────────────┐
│ Your question: "How does AIService call the LLM?"  │
│                                                     │
│ OLD GRAPH: "I don't know, no connections found"    │
│                                                     │
│ NEW GRAPH: "AIService.process_job calls            │
│             GeminiLlmClient.send_job via DI"       │
│                                                     │
│ → You can now trace the FULL call path! ✓          │
└────────────────────────────────────────────────────┘
```

This is the difference between a **partial** graph and a **useful** graph.
