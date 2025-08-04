# Purrfect Platform Architecture Documentation

This document provides a comprehensive explanation of the Purrfect Platform architecture, describing each component and the relationships between them as shown in the architecture diagram.

## Table of Contents

1. [Overview](#overview)
2. [Architecture Components](#architecture-components)
   - [Frontend](#frontend)
   - [API Layer](#api-layer)
   - [Orchestrator](#orchestrator)
   - [Core Agents](#core-agents)
   - [Advanced Agents](#advanced-agents)
   - [Data Stores](#data-stores)
   - [External Services](#external-services)
3. [Component Relationships](#component-relationships)
   - [UI Connections](#ui-connections)
   - [Normal Flow](#normal-flow)
   - [Data Access](#data-access)
   - [Special Connections](#special-connections)
4. [Integration Patterns](#integration-patterns)

## Overview

The Purrfect Platform is a comprehensive educational system built with a multi-agent AI architecture. The system is organized in layers, from user-facing components down to external services, with specialized AI agents working together to deliver various educational features.

## Architecture Components

### Frontend

Frontend components provide the user interface and interaction points for the platform.

| Component | Description |
|-----------|-------------|
| **Dashboard** | Main user interface showing overview of activities, progress, and available tools |
| **Features & Tools** | Access to various platform capabilities and utilities |
| **Exam Q&A Stepper** | Interface for guided exam question answering and learning |
| **Progress & Calendar** | Visualization of learning progress and scheduling tools |
| **Notes Editor** | Interface for creating and managing study notes |
| **Planning Forms** | Interfaces for creating study plans and schedules |
| **Settings & Memory Control** | User preferences and memory/history management |

### API Layer

The API Layer handles incoming requests and manages sessions between the frontend and the system.

| Component | Description |
|-----------|-------------|
| **Auth & Session Controller** | Manages authentication, authorization, and user sessions |
| **ExamAssist Controller** | Handles requests related to exam assistance, including assessment, answering, and completion |
| **Agent Runner Controller** | Dynamically routes requests to appropriate AI agents |
| **Memory Controller** | Manages opt-in memory features, CRUD operations on user data, and audit trails |

### Orchestrator

The Orchestrator coordinates system actions and manages the flow between components.

| Component | Description |
|-----------|-------------|
| **Clawdia Coordinator** | Central coordination system that manages high-level operations |
| **Dynamic Intent Router** | Routes user requests based on detected intents to appropriate agents |
| **Multi-Agent Pipeline** | Manages the workflow and sequencing of multiple agent operations |

### Core Agents

Core Agents provide the fundamental AI capabilities of the platform.

| Agent | Description |
|-------|-------------|
| **AnswerEvaluatorAgent** | Assesses the quality and correctness of user answers |
| **TeachingAgent** | Provides educational content and explanations |
| **PlannerAgent** | Creates study plans and learning paths |
| **FlashcardAgent** | Generates and manages flashcards for spaced repetition learning |
| **CollabAgent** | Facilitates collaborative learning experiences |
| **GameAgent** | Creates educational games and gamified learning experiences |
| **ExamCoachAgent** | Provides guidance and strategies for exam preparation |

### Advanced Agents

Advanced Agents provide specialized capabilities that enhance the core functionality.

| Agent | Description |
|-------|-------------|
| **MetaLearnerAgent** | Analyzes learning patterns and provides meta-cognitive support |
| **CurriculumGeneratorAgent** | Creates comprehensive learning curricula based on goals or exams |
| **SRSAgent** | Implements spaced repetition scheduling for optimized learning |
| **MultimodalIngestAgent** | Processes various content formats (text, images, audio) |
| **EmotionAgent** | Detects and responds to user emotional states |
| **SocialMatchAgent** | Matches users for collaborative learning opportunities |
| **ExplainabilityAgent** | Provides transparency into system decisions and recommendations |
| **ArchivistAgent** | Manages long-term storage and retrieval of user knowledge |
| **ContentCuratorAgent** | Finds and recommends external learning resources |
| **PluginManagerAgent** | Integrates with and manages external plugins and tools |

### Data Stores

Data Stores provide persistent storage for the platform.

| Store | Description |
|-------|-------------|
| **PostgreSQL** | Relational database for structured data, user information, and relationships |
| **Qdrant** | Vector database for semantic search and retrieval of learning materials |

### External Services

External Services extend the platform's capabilities through third-party integrations.

| Service | Description |
|---------|-------------|
| **LLM API** | Large Language Model API for natural language processing |
| **Embeddings API** | Text embedding service for semantic understanding |
| **OCR Service** | Optical Character Recognition for processing images and documents |
| **TTS/STT Service** | Text-to-Speech and Speech-to-Text services |
| **Emotion Detection API** | Service for detecting user emotions |
| **OER / Syllabus APIs** | Open Educational Resources and syllabus information services |
| **Peer Matching Service** | Service for finding appropriate peer matches for collaborative learning |

## Component Relationships

The architecture diagram uses different line styles to indicate different types of relationships:

### UI Connections

UI Connections (dashed lines) represent the flow of user interactions from frontend components to the API layer.

- **Dashboard → API Layer**: User interactions from the dashboard are routed to appropriate controllers
- **Features & Tools → API Layer**: Tool selections trigger API calls to relevant controllers
- **Exam Q&A Stepper → API Layer**: Exam interactions are processed by the ExamAssist Controller
- **Progress & Calendar → API Layer**: Progress tracking and calendar events interact with the Memory Controller
- **Notes Editor → API Layer**: Note creation and editing flow through the Agent Runner Controller
- **Planning Forms → API Layer**: Study planning interactions go through the Agent Runner Controller
- **Settings & Memory Control → API Layer**: Settings changes route through the Auth & Memory Controllers

### Normal Flow

Normal Flow (solid lines) represents the standard processing path for user requests.

- **API Layer → Orchestrator**: Controllers route processed requests to the orchestrator components
  - ExamAssist Controller → Clawdia Coordinator
  - Agent Runner Controller → Dynamic Intent Router
  - Memory Controller → Multi-Agent Pipeline

- **Orchestrator → Agents**: The orchestrator components delegate tasks to appropriate agents
  - Clawdia Coordinator → AnswerEvaluatorAgent, TeachingAgent
  - Dynamic Intent Router → PlannerAgent, FlashcardAgent
  - Multi-Agent Pipeline → MetaLearnerAgent, CurriculumGeneratorAgent

- **Agents → External Services**: Agents use external services for specialized capabilities
  - Most agents connect to LLM API and Embeddings API for core AI functionality

### Data Access

Data Access (dotted lines) shows how components interact with data stores.

- **Core Agents → Data Stores**: All core agents read from and write to both PostgreSQL and Qdrant
- **Advanced Agents → Data Stores**: All advanced agents access both data stores
- **ArchivistAgent → Data Stores**: Special optimized connections for long-term data management

### Special Connections

Special Connections (red dash-dot lines) highlight unique or critical integrations.

- **AnswerEvaluatorAgent → OCR Service**: For processing handwritten or image-based answers
- **MultimodalIngestAgent → OCR Service**: For processing text in images
- **MultimodalIngestAgent → TTS/STT Service**: For processing audio content
- **EmotionAgent → Emotion Detection API**: For analyzing user emotional states
- **SocialMatchAgent → Peer Matching Service**: For finding appropriate learning partners
- **ContentCuratorAgent → OER/Syllabus APIs**: For retrieving external learning resources
- **ArchivistAgent → Data Stores**: Privileged connections for data archiving
- **PluginManagerAgent → Multiple Components**: Connects to multiple system components to extend functionality

## Integration Patterns

The architecture employs several integration patterns:

1. **Layered Architecture**: Clear separation of concerns from frontend to data stores
2. **Microservices**: Components communicate via well-defined APIs
3. **Orchestration**: Central coordination of complex workflows
4. **Event-Driven**: Components respond to user actions and system events
5. **Agent-Based**: Autonomous agents handle specialized tasks
6. **Plugin System**: Extensible architecture via the PluginManagerAgent

This architecture enables the Purrfect Platform to deliver a comprehensive educational experience with flexibility, scalability, and adaptability to user needs.
