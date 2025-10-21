# SEOmax Project Analysis

## Project Overview

SEOmax is a comprehensive SEO analysis platform built on a microservices architecture. The platform enables deep analysis of websites, including content quality, technical health, schema validation, and historical comparisons. This document provides an overview of the project structure, architecture, and key components to help newcomers quickly understand the system.

## Architecture & Services

The project follows a well-structured microservices architecture with the following primary services:

1. **API Service** (`api/main.py`)
   - Central API endpoint handling job management
   - Provides reconciliation and notification capabilities
   - Exposes routes for job creation, status updates, and results retrieval

2. **AI Service** (`ai_service/main.py`)
   - Performs AI-powered content analysis
   - Detects authorship patterns and content quality
   - Integrates with Gemini AI for content evaluation

3. **Aggregator Service** (`aggregator_service/main.py`)
   - Consolidates data from various analysis services
   - Prepares unified reports and insights
   - Handles data processing pipelines

4. **Categorisation Service** (`categorisation_service/main.py`)
   - Classifies web pages by type and purpose
   - Implements categorization algorithms
   - Feeds data to downstream services

5. **Results Service** (`results_service/main.py`)
   - Processes and delivers final analysis results
   - Formats reports for consumption
   - Handles result storage and retrieval

6. **Scraper Service** (`scraper_service/main.py`)
   - Manages web content scraping
   - Handles HTML extraction and storage
   - Captures screenshots for visual analysis

7. **Spider Service** (`spider_service/main.py`)
   - Provides web crawling capabilities
   - Discovers linked pages on target websites
   - Maps site structure for analysis

8. **Validator Service** (`validator_service/main.py`)
   - Validates website schemas and structures
   - Checks for Schema.org compliance
   - Assesses structured data implementation

9. **Wayback Service** (`wayback_service/main.py`)
   - Interacts with the Wayback Machine API
   - Enables historical content comparison
   - Tracks website changes over time

10. **Vitals Service** (`vitals_service/main.py`)
    - Analyzes Core Web Vitals metrics
    - Assesses page performance
    - Evaluates user experience factors

11. **Tech Health Service** (`tech_health_service/main.py`)
    - Evaluates technical health of websites
    - Identifies issues impacting SEO
    - Provides technical recommendations

12. **Start Service** (`start_service/main.py`)
    - Handles job initialization
    - Sets up analysis parameters
    - Triggers the analysis workflow

13. **Dead Letter Service** (`dead_letter_service/main.py`)
    - Processes failed messages/jobs
    - Implements error handling
    - Provides system resilience

## Key Technologies

1. **FastAPI**
   - Used by all services as the web framework
   - Provides async capabilities and automatic API documentation
   - Handles request validation and response formatting

2. **Firestore**
   - Primary database (implemented via the `FirestoreDatabase` class)
   - Stores job data, analysis results, and service state
   - Enables real-time data access across services

3. **Google Cloud Platform Services**
   - PubSub for inter-service communication
   - Cloud Storage for large data and image storage
   - Cloud Tasks for scheduled and delayed processing

4. **Gemini AI**
   - Powers content analysis features
   - Implemented through `gemini_gpt.py`
   - Provides natural language understanding capabilities

5. **Custom Middleware Layer**
   - Includes logging, exception handling, and heartbeat functionality
   - Standardizes behavior across services
   - Provides unified monitoring and error reporting

## Core Data Models

The system operates around several key data models:

1. **Job** (`seomax/models/database.py`)
   - Central entity representing a complete SEO analysis job
   - Contains job configuration, status, and metadata
   - Tracks job progression through the system

2. **PageScrape**
   - Contains scraped HTML content
   - Stores raw page data for analysis
   - May be partitioned for large pages

3. **PageSchema**
   - Holds Schema.org validation results
   - Contains structured data assessment
   - Identifies schema implementation issues

4. **PageCWV**
   - Stores Core Web Vitals metrics
   - Tracks performance measurements
   - Provides UX assessment data

5. **PageComparison**
   - Contains content comparison data
   - Enables historical analysis
   - Identifies content changes over time

6. **PageAuthor**
   - Stores author detection information
   - Contains authorship attribution data
   - Helps assess content authenticity

7. **AIOutputModel**
   - Holds AI analysis results
   - Contains content quality assessments
   - Provides NLP-derived insights

## Communication Pattern

The services utilize a message-based architecture for communication:

- **PubSub** is used for asynchronous communication between services
- Each service processes specific message types based on their responsibilities
- Results are stored in Firestore for retrieval and aggregation
- The system follows an event-driven approach with each service reacting to relevant events

## Notable Design Patterns

1. **Dependency Injection**
   - Extensively used throughout the codebase
   - Facilitates testing and component substitution
   - Improves modularity and code organization

2. **Interface-based Design**
   - Clear separation between interfaces and implementations
   - Enables multiple implementation strategies
   - Supports the Open/Closed principle

3. **Service Pattern**
   - Each service has a corresponding service class (e.g., `AiService`, `ScraperService`)
   - Encapsulates business logic in dedicated service classes
   - Maintains separation of concerns

4. **Repository Pattern**
   - Data access via the `DatabaseConnectionInterface`
   - Abstracts database operations
   - Supports different database implementations

5. **Factory Pattern**
   - Used for creating specific implementations (e.g., `strategy_factory.py`)
   - Centralizes object creation logic
   - Facilitates extension with new implementations

## Processing Flow

Based on the code analysis, the typical job processing flow is:

1. **Job Creation**
   - Via API or StartService
   - Initializes job configuration and metadata
   - Sets up the processing pipeline

2. **Page Categorisation**
   - Determines page types and categories
   - Guides subsequent analysis processes
   - Sets processing expectations

3. **Parallel Processing**
   - Multiple services process the content simultaneously
   - Services include scraping, validation, AI analysis, etc.
   - Each service updates its portion of the job data

4. **Results Aggregation**
   - The Aggregator Service combines data from all services
   - Creates unified analysis reports
   - Prepares final output

5. **Report Generation**
   - Final results are formatted for consumption
   - May include visualization data
   - Delivered via API or storage

This architecture allows for scalable, independent processing of different aspects of SEO analysis.

## Using the code-index-local Tool for Analysis

The `code-index-local` MCP tool provides powerful capabilities for analyzing and understanding the codebase. Here's how to effectively use it:

### Setting Up the Tool

1. **Initialize the Project Path**
   ```python
   use_mcp_tool(
     server_name="code-index-local",
     tool_name="set_project_path",
     arguments={"path": "/path/to/project"}
   )
   ```

2. **Check the Tool Status**
   ```python
   use_mcp_tool(
     server_name="code-index-local",
     tool_name="get_settings_info",
     arguments={}
   )
   ```

### Key Analysis Techniques

1. **Finding Files by Pattern**
   ```python
   use_mcp_tool(
     server_name="code-index-local",
     tool_name="find_files",
     arguments={"pattern": "*.py"}
   )
   ```

2. **Getting File Summaries**
   ```python
   use_mcp_tool(
     server_name="code-index-local",
     tool_name="get_file_summary",
     arguments={"file_path": "api/main.py"}
   )
   ```

3. **Searching Code with Advanced Options**
   ```python
   use_mcp_tool(
     server_name="code-index-local",
     tool_name="search_code_advanced",
     arguments={
       "pattern": "class.*Service",
       "case_sensitive": true,
       "context_lines": 1,
       "file_pattern": "*.py"
     }
   )
   ```

4. **Searching for Database Integration**
   ```python
   use_mcp_tool(
     server_name="code-index-local",
     tool_name="search_code_advanced",
     arguments={
       "pattern": "Firestore|database",
       "case_sensitive": false,
       "context_lines": 1,
       "file_pattern": "*.py"
     }
   )
   ```

### Advanced Analysis Tips

1. **Identifying Service Patterns**
   - Search for class definitions with `"class.*Service"` pattern
   - Look for initialization methods to understand dependencies
   - Examine interface implementations

2. **Understanding Data Flow**
   - Search for database operations to see data persistence patterns
   - Look for messaging code (`PubSub`, `notification`) to trace inter-service communication
   - Examine result processing in aggregator and results services

3. **Exploring API Endpoints**
   - Search for FastAPI route decorators (`@app.get`, `@app.post`)
   - Check dependency injections in route function parameters
   - Analyze request and response models

## Key Findings for Quick Understanding

1. **Service Independence**
   - Each service operates independently and communicates via messaging
   - Services can be deployed, scaled, and maintained separately
   - Failures in one service don't necessarily affect others

2. **Database Centrality**
   - Firestore is the central database for all services
   - The `FirestoreDatabase` class implements the `DatabaseConnectionInterface`
   - Large documents are automatically partitioned to handle Firestore's limitations

3. **Dependency Injection Framework**
   - The codebase uses FastAPI's dependency injection system extensively
   - Common dependencies are defined in the `seomax/base_api/dependencies/` directory
   - Dependencies include database access, notification, and service clients

4. **Error Handling Strategy**
   - Custom exception classes in `seomax/exceptions.py`
   - Exception middleware in `seomax/middleware/exception_middleware.py`
   - Dead Letter Service for processing failed messages

5. **Proxy and Scraping Infrastructure**
   - Proxy handling for accessing blocked sites
   - Screenshot capture capabilities
   - HTML content extraction and storage

6. **Testing Approach**
   - Extensive use of pytest fixtures
   - Mock implementations for external services
   - End-to-end (E2E) tests for service workflows

## Quick Reference: Key Files and Their Purposes

| File/Directory | Purpose |
|----------------|---------|
| `seomax/interfaces/` | Contains interface definitions for key components |
| `seomax/implementations/` | Concrete implementations of the interfaces |
| `seomax/models/` | Data models for various entities and DTOs |
| `seomax/middleware/` | FastAPI middleware components |
| `seomax/constants/` | Configuration constants and enumerations |
| `seomax/services/` | Core business logic services |
| `*/main.py` | Entry points for microservices |
| `api/routes.py` | API endpoint definitions |
| `seomax/cloud_logging/` | Logging infrastructure |

## Common Analysis Tasks and How to Approach Them

1. **Understanding a Service's Responsibilities**
   - Check the service's main.py file
   - Look for handler functions that process specific message types
   - Examine the corresponding service class (e.g., `AiService` for the AI Service)

2. **Tracing a Job's Lifecycle**
   - Start with job creation in the API or Start Service
   - Follow message publishing to subsequent services
   - Examine how results are aggregated and presented

3. **Understanding Data Models**
   - Examine the `seomax/models/database.py` file for core models
   - Look at service-specific models in their respective directories
   - Check for model relationships and inheritance

4. **Analyzing API Endpoints**
   - Start with `api/routes.py`
   - Look for route handlers and their dependencies
   - Check request/response schemas in `api/schemas.py`

By using these techniques and focusing on these key areas, you can quickly gain a comprehensive understanding of the SEOmax codebase and architecture.
