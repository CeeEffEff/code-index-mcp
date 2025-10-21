# AI Service Exploration Findings

**Date**: 2025-01-16  
**Purpose**: Document Neo4j graph database exploration to understand ai_service architecture for local evaluation integration

---

## 1. Graph Database Structure

### Node Labels
- **Class**: Represents classes in the codebase
- **Function**: Represents methods/functions
- **File**: Source files
- **Symbol**: General symbols
- **Configuration**: Configuration-related nodes
- **Cluster, ClusterStatistics**: Code organization metadata
- **Memory, IndexMetadata**: Database metadata
- **PullRequest**: Version control metadata
- **Numeric labels (0-9)**: Unknown classification system

### Relationship Types
- **CALLS**: Function call relationships (critical for tracing flow)
- **CONTAINS**: Class contains methods
- **CLASS_TYPE**: Type relationships
- **DECORATES**: Decorator relationships
- **HAS_CLUSTER**: Clustering relationships
- **HAS_METHOD**: Method ownership
- **MODIFIES**: Modification relationships

---

## 2. AIService Core Architecture

### Main AIService Methods (26 total)
```python
AIService.__init__
AIService.run_service              # Entry point
AIService.init_stats_w_assets      # Initialize statistics
AIService.try_get_valid_asset      # Asset validation
AIService.relevant_question_configs # Filter questions
AIService.relevant_module_configs   # Filter modules
AIService.generate_questions        # Create question objects
AIService.generate_question         # Create single question
AIService.process_questions         # Main processing loop
AIService.propagate_existing_answers # Use cached answers
AIService.retrieve_attributes       # Get/generate attributes
AIService.generate_attributes       # Generate attributes
AIService.run_generate_attributes   # Run attribute generation
AIService.process_job               # Process LLM job
AIService.propagate_results         # Distribute results
AIService.propagate_all_results     # Handle non-grouped results
AIService.triage_results            # Sort valid/invalid
AIService.propagate_groups          # Handle grouped questions
AIService.triage_groups             # Validate groups
AIService.get_answer_for_question   # Resolve answer
AIService.get_result_from_subtask   # Execute subtasks
AIService.propagate_to_job_result   # Aggregate results (MOST IMPORTANT - 0.35 PageRank)
AIService.update_question           # Update database (0.29 PageRank)
AIService.log_question_status       # Logging
AIService.max_attempts              # Config property
AIService.question_expiry_seconds   # Config property
```

### Call Relationships from run_service
From `AIService.run_service` directly calls:
1. `init_stats_w_assets` - Setup statistics
2. `try_get_valid_asset` - Validate assets
3. `relevant_question_configs` - Filter questions
4. `generate_questions` - Create question objects
5. `process_questions` - Main loop

### Call Relationships from process_questions
From `AIService.process_questions` directly calls:
1. `propagate_existing_answers` - Use cached answers
2. `retrieve_attributes` - Get/generate attributes
3. `defaultdict` - Data structure (Python builtin)

**Note**: Graph appears incomplete - expected to see `process_job` called from `process_questions` but relationship not found in graph.

### Call Relationships from process_job
From `AIService.process_job` directly calls:
1. `propagate_results` - Handle LLM response

**Note**: Expected to see LLM invocation or job iteration but not found in graph.

---

## 3. LLM Integration Layer

### GeminiLlmClient Methods
```python
GeminiLlmClient.__init__
GeminiLlmClient.__create_config     # Create model config
GeminiLlmClient.__encode_prompt_images # Handle images
GeminiLlmClient.__parse_response    # Parse LLM response
GeminiLlmClient.__load_model_response # Load response data
GeminiLlmClient.get_string_token_length # Token counting
GeminiLlmClient.send_job            # PRIMARY LLM INVOCATION METHOD
GeminiLlmClient.send_msg_raw        # Raw message sending
```

### LLM-Related Classes
```python
GeminiLlmClient         # The actual LLM client
LlmClientInterface      # Interface definition
GeminiResponse          # Response data model
LlmJsonResponse         # JSON response wrapper
BaseLlmJobParameters    # Job parameters base
BaseMultiModalLlmJobParameters # Multimodal params
LLMJobCommander         # Job orchestration
LLMJobFactory           # Job creation
LlmJobInterface         # Job interface
LlmSystemException      # Error handling
```

### LLMJobCommander Methods
```python
LLMJobCommander.__init__
LLMJobCommander._build_job_config
LLMJobCommander._get_job_config
LLMJobCommander.add_question
LLMJobCommander.set_questions
LLMJobCommander.iter_jobs          # Iterate over jobs
LLMJobCommander.job_configs
```

### Critical Finding: Missing Link + Dependency Injection Pattern

**ISSUE**: The graph does not show direct CALLS relationships between:
- AIService methods → LLMJobCommander methods
- AIService methods → GeminiLlmClient.send_job
- LLMJobCommander → GeminiLlmClient.send_job

**DISCOVERY**: Found dependency injection functions that provide GeminiLlmClient:
- `dependency_gemini` - Base dependency injector
- `service_dependency_gemini` - Service-level DI (called by `catch_and_raise`)
- `no_cache_service_dependency_gemini` - No-cache variant DI (called by `catch_and_raise`)

This explains the missing link: **GeminiLlmClient is provided through dependency injection**, not direct instantiation. The service likely receives the LLM client through constructor injection or function parameters.

**Interface Discovery**:
- `LlmClientInterface` defines the contract with methods:
  - `send_job` (primary LLM invocation)
  - `send_msg_raw` (raw message sending)
  - `get_string_token_length` (token counting)
  - `log_prompts` (logging)
- `LlmJobInterface` defines job structure with:
  - `message_prompt`, `message_prompt_template`
  - `system_prompt`
  - `response_json_schema`
  - `params_type`, `response_type`

This suggests either:
1. Graph generation was incomplete for polymorphic calls
2. Calls are indirect (through interfaces/abstractions) ✓ CONFIRMED
3. Calls happen via dependency injection ✓ CONFIRMED
4. The actual invocation uses a pattern that wasn't captured

---

## 4. Data Models

### Core Entity Classes
```python
Asset              # The asset being analyzed
BaseAsset          # Base asset class
AssetAttributes    # Attribute storage
AssetAttribute     # Single attribute
AssetMetadata      # Asset metadata
AssetType          # Type classification
AssetTypeBackend   # Backend handling
AssetMap           # Asset mapping
AssetRule          # Business rules

Question           # Question object
QuestionConfiguration  # Question config
CustomQuestion     # Custom question type
QuestionModuleName # Module association

Answer             # Answer object
AnswerEvaluationService # Answer evaluation

Module             # Analysis module
ModuleConfiguration    # Module config
ModuleLoader       # Loads modules/questions
ServiceModule      # Module wrapper

AiAnalysisJob      # Job tracking
BaseAiAnalysisJob  # Base job class
AiAnalysisJobParameters # Job parameters
AttributeGenerationJobParameters # Attribute job params
```

### Configuration Classes
```python
Config (2 instances)   # Configuration objects
BaseJobConfiguration   # Job config base
EvaluateAssetJobConfiguration # Evaluation config
JobConfiguration       # Job config
FanoutConfig          # Fanout configuration
FanoutConfigInterface # Fanout interface
PubSubConfigPayload   # PubSub config
```

### ModuleLoader Methods
```python
ModuleLoader.questions_from_df        # Load questions from DataFrame (61.3 betweenness)
ModuleLoader.question_configurations_map  # Map configurations
ModuleLoader.module_generator         # Generate modules
ModuleLoader.custom_configuration     # Custom configs
ModuleLoader.explode_delimited        # Parse delimited data
ModuleLoader.log_and_return          # Logging utility
```

---

## 5. Database Interaction Points

### Primary Database Method
- `AIService.update_question` - Called by:
  - `propagate_all_results`
  - `triage_groups`

### Attribute Caching
- `AIService.retrieve_attributes` - Checks DB for cached attributes
- `AIService.generate_attributes` - Generates new attributes if not cached
- `AIService.run_generate_attributes` - Executes attribute generation

### Answer Caching
- `AIService.propagate_existing_answers` - Reuses cached answers

**Critical Constraint**: All these methods interact with a cloud database. For local execution, we need to:
1. Mock/stub database operations
2. Use in-memory storage
3. Skip caching entirely for evaluation

---

## 6. Key Insights from GDS Analysis

### PageRank (Importance)
1. **propagate_to_job_result** (0.349) - Central hub for result aggregation
2. **update_question** (0.293) - Main database updater
3. **get_result_from_subtask** (0.249) - Subtask coordination
4. **generate_question** (0.214) - Question factory
5. **triage_results** (0.205) - Result sorting

### Betweenness Centrality (Bottlenecks)
1. **AIService** class (144.75) - Root of all operations
2. **GeminiLlmClient** (100.0) - **CRITICAL: All LLM calls bottleneck here**
3. **AssetEvaluationCommander** (84.0) - Evaluation orchestration
4. **AIService.__init__** (52.2) - Initialization
5. **process_questions** (49.8) - **Main processing loop**
6. **ModuleLoader.questions_from_df** (61.3) - Configuration loading

---

## 7. Service Flow (from Documentation)

### High-Level Flow
1. **Initialize**: `init_stats_w_assets`, validate assets
2. **Configure**: `relevant_question_configs`, `generate_questions`
3. **Cache Check**: `propagate_existing_answers`
4. **Attributes**: `retrieve_attributes`, `generate_attributes` (LLM call)
5. **Filter**: Run AFTER_ATTRIBUTES subtasks
6. **Process**: `process_questions` → `process_job` → LLM invocation
7. **Validate**: `propagate_results`, `triage_results`, `triage_groups`
8. **Store**: `update_question`, `propagate_to_job_result`
9. **Retry**: Loop back if invalid responses (max attempts check)

### Retry Mechanism
- Max attempts configuration
- Invalid responses trigger retry
- Grouped questions have special validation (exactly one answer must be true)

---

## 8. Cloud Resource Dependencies

### Confirmed Cloud Resources
1. **Database** (Primary Concern)
   - `update_question` - Writes to DB
   - `retrieve_attributes` - Reads from DB
   - `propagate_existing_answers` - Reads cached answers from DB
   - Answer/question persistence

2. **Generative Model** (ALLOWED)
   - `GeminiLlmClient.send_job` - This is the ONLY cloud resource we should use
   - Model API calls via Google AI API or Vertex AI

3. **Potential Additional Resources** (Need to verify)
   - Asset storage (if assets are fetched from cloud)
   - Configuration storage (if configs are remote)
   - Pub/Sub systems (for job orchestration)
   - Asset metadata services

---

## 9. Questions Requiring Code Review

Since the graph is incomplete, we need to examine actual source code to understand:

1. **How does AIService.process_job actually invoke the LLM?**
   - Does it use LLMJobCommander.iter_jobs?
   - How does it get from AIService → GeminiLlmClient.send_job?

2. **What are the input requirements for run_service?**
   - Asset object structure
   - Configuration format (DataFrame? Dict? Custom objects?)
   - Required vs optional parameters

3. **What does the output look like?**
   - JobResult structure
   - Answer format
   - Statistics returned

4. **How are prompts constructed?**
   - Template system
   - How attributes are incorporated
   - How questions are formatted

5. **Can we isolate the LLM invocation logic?**
   - Can we extract just the prompt construction + LLM call?
   - Can we bypass all the database/caching logic?

---

## 10. Proposed Integration Strategy

### Option 1: Minimal Extraction (Recommended)
Extract only the essential components:
1. Prompt construction logic
2. LLM invocation (GeminiLlmClient)
3. Response parsing
4. Skip all database operations
5. Skip caching
6. Skip statistics/tracking
7. Use simplified question/answer objects

**Pros**: Clean, minimal dependencies, no cloud resources except LLM  
**Cons**: Doesn't test full production logic

### Option 2: Full Service with Mocks
Use the complete AIService but mock dependencies:
1. Mock database layer (in-memory dict)
2. Mock configuration loading (provide configs directly)
3. Mock asset fetching (provide assets directly)
4. Keep full retry/validation logic
5. Keep GeminiLlmClient for actual LLM calls

**Pros**: Tests real production flow, validates full logic  
**Cons**: Complex setup, many mocks needed, potential hidden dependencies

### Option 3: Hybrid Approach
1. Extract core classes: Question, Answer, Asset (simplified versions)
2. Extract LLM invocation: GeminiLlmClient
3. Extract essential flow: question generation → LLM call → answer parsing
4. Skip: database, caching, full retry logic, statistics
5. Implement minimal config: simple dict-based configs

**Pros**: Balance of realism and simplicity  
**Cons**: May miss edge cases in production logic

---

## 11. Next Steps

### Immediate Actions
1. **Locate source code files** for critical classes:
   - AIService
   - GeminiLlmClient  
   - LLMJobCommander
   - Question/Answer models

2. **Trace actual execution path** in code:
   - From process_job to LLM invocation
   - Identify all required parameters
   - Map data transformations

3. **Identify minimal dependencies**:
   - What can we skip?
   - What must we keep?
   - What can we simplify?

4. **Design adapter layer**:
   - How evaluation framework talks to ai_service
   - Input format translation
   - Output format translation

5. **Prototype implementation**:
   - Start with Option 3 (Hybrid)
   - Test with single evaluation example
   - Iterate based on findings

---

## 12. Key Takeaways

1. **GeminiLlmClient is the gateway** - All LLM calls go through here (betweenness: 100)
2. **process_questions is the main loop** - Core processing logic (betweenness: 49.8)
3. **propagate_to_job_result is the hub** - Result aggregation point (PageRank: 0.35)
4. **Database interactions are pervasive** - update_question, retrieve_attributes, propagate_existing_answers
5. **Graph is incomplete** - Missing critical CALLS relationships between components
6. **Configuration is complex** - ModuleLoader loads from DataFrames
7. **Retry mechanism exists** - Max attempts, grouped question validation
8. **Multiple data models** - Asset, Question, Answer, Configuration, Module

---

## Graph Database Limitations Encountered

1. **Missing CALLS relationships** between AIService and LLM layer
2. **No visibility into interface implementations** (polymorphic calls not captured)
3. **Limited to static analysis** (runtime behavior not captured)
4. **Incomplete coverage** (some methods/classes may be missing)

**Conclusion**: Neo4j graph provides excellent structural overview but requires source code review to understand complete execution flow and LLM invocation path.
