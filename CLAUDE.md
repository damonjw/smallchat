# Mini-Agent: A Minimal Coding Assistant

This repository contains a minimal implementation of an LLM-based coding assistant that replicates Claude Code's behavior in just ~280 lines of agent code, 400 lines of tools, and 1200 lines of prompts.

## Overview

Mini-agent demonstrates that the behavior of an AI agent is completely characterized by only five things sent to the LLM completion method:
1. **System prompt** - Instructions and behavior guidelines
2. **Tool descriptions** - Available functions and their schemas  
3. **User prompt** - What the user types in
4. **Tool results** - Outputs from executed tools
5. **System reminders** - Automatically inserted contextual information

## Architecture

The system consists of four main components:

### Core Files

- **`mini_agent.py`** (280 lines): Main interaction loop that handles user input, communicates with LLMs, and orchestrates tool execution
- **`core_tools.py`** (400+ lines): Implements all core tools (Read, Write, Edit, Grep, Glob, LS, Bash, WebFetch, WebSearch, TodoWrite, etc.)  
- **`adapter.py`**: Model-agnostic interface using `litellm` library to connect to different LLMs (GPT, Claude, Gemini)
- **`typedefs.py`**: Type definitions for messages, tools, transcripts, and hook systems

### Key Design Patterns

#### 1. Two-Loop Architecture
The agent operates with nested loops in `mini_agent.py:102-111`:

1. **Inner "agentic" loop** (`agentic_loop`): Gets LLM responses, executes tools, presents results back to LLM, repeats until no more tool requests
2. **Outer "user interaction" loop** (`main`): Gets user prompts, runs agentic loop, repeats for next user input

#### 2. MCP Integration
All behavior is expressed through Model Context Protocol (MCP):
- Tools are MCP servers accessible via `--mcp` flag
- System prompts and reminders delivered through MCP resource system  
- Hooks implemented as MCP resource reads (e.g., `plan-mode://set/true`)

#### 3. Hook System
Three types of hooks modify behavior at runtime:
- **`UserPromptSubmit`**: Adds context before LLM processing (file changes, TODO reminders, etc.)
- **`PreToolUse`**: Controls tool execution permissions  
- **`PostToolUse`**: Handles tool result processing

## How It Works

### Message Flow
1. User enters prompt in main loop (`mini_agent.py:46-47`)
2. `user_prompt_hook` invokes UserPromptSubmit hooks to add context (`mini_agent.py:115-132`)
3. `agentic_loop` sends messages to LLM via `adapter.acompletion` (`mini_agent.py:69-103`)
4. LLM response parsed for tool calls (`mini_agent.py:85-94`)
5. Each tool invoked through `invoke_tool` with Pre/Post hooks (`mini_agent.py:133-189`)
6. Results fed back to LLM until no more tools requested
7. Final response displayed to user

### Tool Implementation
Tools in `core_tools.py` follow consistent pattern:
```python
def tool_impl(input: dict[str, Any]) -> Tuple[bool, list[mcp.types.ContentBlock]]:
    # Validate input, perform operation, return (success, content)
```

Key tools include:
- **File Operations**: `Read` (line 127), `Write` (line 260), `Edit` (line 351), `MultiEdit` (line 434)
- **Search**: `Grep` (line 619), `Glob` (line 517), `LS` (line 718)  
- **Execution**: `Bash` (line 1151), `Task` (subagent, line 1075)
- **Web**: `WebFetch` (line 1208), `WebSearch` (line 1279)
- **Planning**: `TodoWrite` (line 887), `ExitPlanMode` (line 928)

### State Management
- **Transcript**: Conversation history stored in JSONL format, compatible with Claude Code
- **File Tracking**: `known_content_files` and `stale_content_files` track file modifications for notifications
- **Plan Mode**: Global flag toggled via `plan-mode://set/{true|false}` resource

### LLM Integration  
`adapter.py` provides model-agnostic completion:
- Supports prompt caching for efficiency (lines 23-44)
- Converts between internal message format and model APIs
- Handles tool calling across different model providers

## Key Features

### Same Mechanics as Claude Code
- Identical tool behavior and system prompt structure
- Compatible transcript format for migration between systems
- Supports hooks, subagents, and all core tools

### Missing "Secret Sauce"
While mechanically identical, mini-agent uses simplified versions of:
- Tool descriptions and schemas
- System prompts and behavioral instructions  
- System reminders and contextual hints

### Supported Operations
- File manipulation with change tracking
- Code search and navigation
- Command execution with safety hooks
- Web browsing and search
- TODO list management  
- Plan mode for complex tasks
- Subagent spawning for specialized tasks

## Usage Examples

```bash
# Basic usage
export GEMINI_API_KEY=your_key
./mini_agent.py --model gemini/gemini-2.5-pro

# Resume from transcript  
./mini_agent.py --resume transcript.jsonl --model anthropic/claude-sonnet-4

# Non-interactive mode
./mini_agent.py --no-interactive -p "What files are in the current directory?"
```

The system demonstrates that sophisticated AI agent behavior emerges from the interaction between a simple execution loop and well-designed tool interfaces, rather than complex agent logic.
- Whenever you need to update PLAN.md, do so. Don't bother asking for permission. Just let me know afterwards that it's been updated.