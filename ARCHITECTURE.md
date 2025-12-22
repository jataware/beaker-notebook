# Beaker Kernel Architecture

## Overview

Beaker Kernel is an extensible Jupyter kernel that provides enhanced computational capabilities through AI-powered contexts, multi-language subkernels, and intelligent code analysis. Built on top of Jupyter Server infrastructure, it supports both standalone notebook mode and multi-user server deployments.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Client Layer                            │
│  (JupyterLab, Notebook, API clients)                        │
└─────────────────────┬───────────────────────────────────────┘
                      │ HTTP/WebSocket
┌─────────────────────▼───────────────────────────────────────┐
│                  Application Layer                          │
│  ┌─────────────────┬─────────────────┬─────────────────┐    │
│  │  Web Server     │   CLI Tools     │  API Handlers   │    │
│  │  (Tornado)      │                 │                 │    │
│  └─────────────────┼─────────────────┼─────────────────┘    │
└──────────────────┬─┼─────────────────┼─────────────────┬────┘
                   │ │                 │                 │
┌──────────────────▼─▼─────────────────▼─────────────────▼────┐
│                    Services Layer                           │
│  ┌──────────┬──────────┬──────────┬──────────┬──────────┐  │
│  │ Session  │ Kernel   │ Context  │ Storage  │Datastore │  │
│  │ Manager  │ Manager  │ Manager  │ & Auth   │          │  │
│  └──────────┴──────────┴──────────┴──────────┴──────────┘  │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                  Core Kernel Layer                          │
│  ┌─────────────────┬─────────────────┬─────────────────┐    │
│  │  BeakerKernel   │   Contexts      │   SubKernels    │    │
│  │  (Proxy Mgr)    │   (AI Agents)   │   (Languages)   │    │
│  └─────────────────┼─────────────────┼─────────────────┘    │
└──────────────────┬─┼─────────────────┼─────────────────┬────┘
                   │ │                 │                 │
┌──────────────────▼─▼─────────────────▼─────────────────▼────┐
│                   Extension Layer                           │
│  (Autodiscovery system for contexts, subkernels, etc.)      │
└─────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
beaker_kernel/
├── kernel.py              # Main kernel implementation
├── app/                   # Application interface layer
│   ├── api/              # REST API handlers
│   ├── ui/               # Web UI assets
│   ├── base.py          # Base application class
│   ├── server_app.py    # Production server
│   ├── notebook_app.py  # Notebook server
│   ├── dev_app.py       # Development server with hot reload
│   ├── multiuser_app.py # Multi-user server
│   └── handlers.py      # Web request handlers
├── services/             # Business logic services
│   ├── kernel/          # Kernel lifecycle management
│   ├── session/         # Session management
│   ├── context/         # Context discovery and management
│   ├── auth/            # Authentication providers
│   ├── storage/         # Storage backends
│   └── datastore/       # Data persistence layer
├── lib/                 # Core library components
│   ├── code_analysis/   # Static code analysis
│   ├── integrations/    # External integrations
│   ├── exporters/       # Notebook exporters
│   ├── templates/       # Code generation templates
│   ├── context.py       # Context (AI agent) framework
│   ├── subkernel.py     # Language subkernel framework
│   ├── agent.py         # AI agent base classes
│   ├── agent_tasks.py   # Agent task definitions
│   ├── config.py        # Configuration management
│   ├── jupyter_kernel_proxy.py  # Kernel proxy infrastructure
│   ├── message_types.py # Message type definitions
│   ├── types.py         # Type definitions
│   ├── workflow.py      # Workflow management
│   ├── extension.py     # Extension system
│   ├── app.py           # Application utilities
│   ├── admin.py         # Administrative functions
│   ├── autodiscovery.py # Extension autodiscovery
│   └── utils.py         # Utility functions
├── contexts/            # Built-in AI contexts
├── subkernels/         # Built-in language subkernels
├── cli/                # Command-line interface
├── builder/            # Build system integration
└── util/               # Utility modules
```

## Core Components

### 1. Application Layer (`app/`)

The application layer provides different deployment modes and interfaces:

**Base Application** (`base.py`):
- `BaseBeakerApp`: Foundation class for all Beaker applications
- Configures Jupyter Server components with Beaker-specific services
- Handles traitlet configuration and extension loading

**Application Types**:
- **Server App**: Production-ready server with optimized defaults
- **Notebook App**: Local development with notebook interface
- **Dev App**: Development mode with file watching and auto-reload
- **Multiuser App**: Multi-user deployment with enhanced authentication

**API Layer** (`api/`):
- RESTful endpoints for kernel management, notebook operations
- Integration with external services
- Handler discovery and registration system

### 2. Services Layer (`services/`)

Provides business logic and manages system resources:

**Session Management** (`session/`):
- `BeakerSessionManager`: Extends Jupyter's session management
- Handles session pruning and kernel environment setup
- Manages session-specific configuration and state

**Kernel Services** (`kernel/`):
- `BeakerKernelManager`: Manages individual kernel lifecycles
- `BeakerKernelMappingManager`: Maps sessions to kernels
- `BeakerKernelSpecManager`: Handles kernel specification discovery
- `BeakerKernelProvisioner`: Provisions and manages kernel resources

**Context Services** (`context/`):
- `ContextManager`: Manages context lifecycle and state
- `ContextDiscoveryService`: Discovers and loads available contexts
- Context request handlers for API integration

**Authentication** (`auth/`):
- Pluggable authentication providers
- Notebook-based authentication for local development
- Cognito integration for enterprise deployments
- Dummy authentication for testing

**Storage** (`storage/`):
- Persistent storage backends for notebooks and state
- Configurable storage providers

**Datastore** (`datastore/`):
- Abstract data persistence layer with multiple backend support
- DynamoDB backend for cloud deployments
- SQLite backend for local development
- In-memory backend for testing
- Record management and data modeling

### 3. Core Kernel Layer

The heart of Beaker's computational capabilities:

**BeakerKernel** (`kernel.py` at root):
- Extends `KernelProxyManager` from `lib/jupyter_kernel_proxy.py`
- Intercepts and enhances Jupyter messages with AI capabilities
- Coordinates between contexts, subkernels, and the base Jupyter infrastructure
- Manages execution context and message routing

**Context System** (`lib/context.py`):
- `BeakerContext`: Base class for AI-powered execution contexts
- Provides tools, workflows, and intelligent code assistance
- Integrates with external AI services and models
- Supports code analysis, generation, and interactive assistance

**SubKernel System** (`lib/subkernel.py`):
- `BeakerSubkernel`: Base class for language-specific execution engines
- Manages code execution, state persistence, and environment isolation
- Supports checkpointing and state management across executions

**Agent System** (`lib/agent.py`, `lib/agent_tasks.py`):
- AI agent base classes and task definitions
- Integration with agent frameworks
- Task execution and management

**Configuration** (`lib/config.py`):
- Centralized configuration management with environment support
- Dynamic configuration updates and validation
- Integration with Jupyter's traitlet system

**Supporting Infrastructure** (`lib/`):
- `jupyter_kernel_proxy.py`: Kernel proxy pattern implementation
- `message_types.py`: Message type definitions and handling
- `types.py`: Shared type definitions
- `workflow.py`: Workflow management system
- `extension.py`: Extension system framework
- `autodiscovery.py`: Dynamic extension discovery
- `utils.py`: Common utility functions

### 4. Extension System

**Autodiscovery** (`lib/autodiscovery.py`):
- Dynamic discovery and loading of contexts and subkernels
- Entry point-based extension system
- Graceful error handling for missing or broken extensions

**Built-in Extensions**:
- **Contexts** (`contexts/`): Default AI-powered context with agents
- **SubKernels** (`subkernels/`): Python, R, Julia language support

## Key Design Patterns

### 1. Proxy Pattern
The `BeakerKernel` acts as a proxy to standard Jupyter kernels, intercepting and enhancing messages with AI capabilities while maintaining compatibility.

### 2. Plugin Architecture
Extensible through autodiscovery of contexts and subkernels via Python entry points, allowing third-party extensions.

### 3. Service-Oriented Architecture
Clear separation between application interface, business services, and core kernel functionality.

### 4. Configuration-Driven
Extensive use of traitlets for runtime configuration, supporting both development and production deployments.

## Message Flow

```
Client Request
    │
    ▼
Web Server (Tornado)
    │
    ▼
API Handler
    │
    ▼
Service Layer
    │
    ▼
BeakerKernel (Proxy)
    │
    ├─────────────────┬─────────────────┐
    ▼                 ▼                 ▼
Context System    SubKernel        Standard Jupyter
(AI Agent)       (Language)         Kernel
    │                 │                 │
    ▼                 ▼                 ▼
Response Processing & Enhancement
    │
    ▼
Client Response
```

## Configuration System

Beaker uses a multi-layer configuration system:

1. **Default Configuration**: Built-in defaults for all components
2. **Environment Variables**: Runtime configuration via environment
3. **Configuration Files**: Python-based configuration files
4. **CLI Arguments**: Command-line overrides
5. **Runtime Updates**: Dynamic configuration changes

Configuration is managed through:
- Jupyter's traitlet system for type safety and validation
- Environment variable integration
- File-based configuration with Python syntax

## Security Model

- **Authentication**: Pluggable authentication providers
- **Code Analysis**: Static analysis for security and trust evaluation
- **Sandboxing**: Isolated execution environments for subkernels
- **Input Validation**: Message and code validation before execution

## Extension Development

### Creating a Context

```python
from beaker_kernel.lib.context import BeakerContext

class MyContext(BeakerContext):
    def __init__(self, beaker_kernel, config):
        super().__init__(beaker_kernel, config)
        # Initialize your AI agents, tools, etc.

    async def setup(self):
        # Async initialization
        pass
```

### Creating a SubKernel

```python
from beaker_kernel.lib.subkernel import BeakerSubkernel

class MySubkernel(BeakerSubkernel):
    language = "mylang"

    async def execute(self, code):
        # Execute code in your language
        return result
```

### Registration

Extensions are registered via entry points in `pyproject.toml`:

```toml
[project.entry-points."beaker_kernel.contexts"]
my_context = "my_package.context:MyContext"

[project.entry-points."beaker_kernel.subkernels"]
my_subkernel = "my_package.subkernel:MySubkernel"
```

## Deployment Modes

### Development Mode
```bash
beaker dev watch  # File watching with auto-reload
```

### Local Notebook Mode
```bash
beaker notebook  # Single-user notebook interface
```

### Production Server Mode
```bash
beaker server start server --port 8888  # Multi-session server
```

### Multi-User Mode
```bash
beaker server start multiuser  # Enterprise deployment
```

## Dependencies

### Core Dependencies
- **Jupyter Infrastructure**: `jupyterlab`, `jupyterlab-server`
- **Web Framework**: `tornado` (async web server)
- **AI Integration**: `archytas` (agent framework)
- **Configuration**: Built on Jupyter's traitlet system
- **Development**: `watchdog` (file watching), `click` (CLI)

### Optional Dependencies
- Language subkernels (Python, R, Julia specific packages)
- AI model providers (OpenAI, Anthropic, etc.)
- External integrations (databases, APIs)

## Future Architecture Considerations

This architecture supports future enhancements including:
- Distributed kernel execution
- Enhanced AI model integration
- Real-time collaboration features
- Advanced security and sandboxing
- Performance monitoring and optimization
- Custom UI components and extensions

The modular design ensures that new capabilities can be added without disrupting existing functionality, maintaining backward compatibility while enabling innovation.
