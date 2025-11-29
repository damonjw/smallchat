# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This codebase contains an LLM-based agentic assistant as a thought experiment to showcase the mechanisms behind Claude Code. It is NOT a production system and has no users. The project explores complex agentic behaviors through two implementations:

- **v2 (root level)**: New architecture implementing persistent subagents with multi-agent discussions
- **v1 (subdirectory)**: Original implementation demonstrating Claude Code's core mechanics

## Documentation

- `doc/GOALS.md`: Research goals and use cases for multi-agent behaviors
- `doc/PLAN.md`: Detailed architectural design for v2 (hooks, subagents, discussions)
- `v1/ARCHITECTURE.md`: Architecture of the v1 implementation
- `v1/README.md`: Usage and implementation details for v1

## Key Architectural Concepts

### V2 Architecture (Current)

The new architecture (root level files) is built on simple primitives designed for complex emergent behavior:

**Core Components:**
- `agent.py`: Implements `Agent` and `World` classes. Agents maintain transcripts and can spawn persistent subagents
- `prompts.py`: Tool descriptions for `task` and `discuss` actions
- `utils.py`: Helper functions including `function_to_tool` (converts Python functions to LiteLLM tool schemas), `spinner`, and `as_described` decorator

**Key Design Patterns:**
1. **Persistent Subagents**: Unlike v1, subagents persist across multiple interactions and can be queried repeatedly
2. **Multi-Agent Discussions**: The `discuss` tool enables multiple subagents to participate in structured conversations
3. **Simple Primitives**: Two core types (Agent, World) enable rich emergent behaviors
4. **Async Architecture**: Full async/await support for parallel operations

**Actions:**
- `task`: Create a new persistent subagent with custom system prompt
- `discuss`: Chair a round of discussion among subagents (speakers and listeners)

### V1 Architecture (Reference Implementation)

Located in `v1/` subdirectory, demonstrates that AI agent behavior is characterized by five things sent to the LLM:
1. System prompt
2. Tool descriptions
3. User prompt
4. Tool results
5. System reminders

**Core Files:**
- `v1/mini_agent.py` (280 lines): Main interaction loop with two-loop architecture (inner agentic loop + outer user interaction loop)
- `v1/core_tools.py` (400+ lines): All core tools (Read, Write, Edit, Grep, Glob, LS, Bash, WebFetch, WebSearch, TodoWrite, etc.)
- `v1/adapter.py`: Model-agnostic LiteLLM interface with prompt caching support
- `v1/typedefs.py`: Type definitions for messages, tools, transcripts, hooks

**Hook System:**
- UserPromptSubmit: Adds context before LLM processing
- PreToolUse: Controls tool execution permissions
- PostToolUse: Handles tool result processing

## Running the Code

### V2 (New Architecture)
```bash
# Set up environment
export ANTHROPIC_API_KEY=your_key

# Run the agent
python3 agent.py
```

### V1 (Reference Implementation)
```bash
# Set up virtual environment
cd v1
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run with different models
export GEMINI_API_KEY=your_key
./mini_agent.py --model gemini/gemini-2.5-pro

export ANTHROPIC_API_KEY=your_key
./mini_agent.py --model anthropic/claude-sonnet-4

# Resume from transcript
./mini_agent.py --resume transcript.jsonl --model <model>

# Non-interactive mode
./mini_agent.py --no-interactive -p "What files are in the current directory?"
```

## Testing

V1 has comprehensive test coverage in `v1/test/`:
```bash
cd v1
pytest test/test_*.py
```

Tests cover: agent behavior, file operations (read/write/edit/multiedit), search (grep/glob), directory listing, and more.

## Dependencies

Key dependencies (see `v1/requirements.txt`):
- `litellm`: Model-agnostic LLM interface
- `mcp`: Model Context Protocol for tools and resources
- `pydantic`: Type validation
- `pytest-asyncio`: Async testing support

## Design Philosophy

This is a **research platform** for exploring agentic behaviors:
- **Simple implementation, complex behavior**: Few primitives (Agent, World) enable sophisticated emergent behaviors
- **Rapid prototyping**: Behaviors can be specified in natural language (system prompts) rather than code
- **Homoiconic design**: Agents can create and modify other agents' prompts and behaviors
- **Not for production**: Focus is on exploration and understanding, not robustness or safety

The v1 implementation proves that Claude Code's behavior can be replicated with minimal code (280 lines for the agent loop, 400 for tools), demonstrating that sophistication comes from well-designed tool interfaces and prompts rather than complex agent logic.

The v2 architecture extends this to enable multi-agent scenarios: debates, resource constraints, steel-man reasoning, long-term memory, event-driven agents, Socratic teaching, and strategic thinking.
