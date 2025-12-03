# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This codebase contains an LLM-based agentic assistant as a thought experiment to showcase the mechanisms behind Claude Code. It is NOT a production system and has no users. The project explores complex agentic behaviors. The codebase comes in two parts: Python code (smallchat.py and agent.py others) for running the agentic system, and a Javascript-based viewer app (in the viewer subdirectory).

### Documentation

- `doc/GOALS.md`: Research goals and use cases for multi-agent behaviors
- `doc/PLAN.md`: Detailed architectural roadmap (hooks, subagents, discussions)
- `viewer/README.md`: Design document for the viewer app

## Design Philosophy

 This is a **research platform** for exploring agentic behaviors:
- **Simple implementation, complex behavior**: Few primitives (Agent, World) enable sophisticated emergent behaviors
- **Rapid prototyping**: Behaviors can be specified in natural language (system prompts) rather than code
- **Homoiconic design**: Agents can create and modify other agents' prompts and behaviors
- **Not for production**: Focus is on exploration and understanding, not robustness or safety


## Historical (v1) version

There is another historical implementation of the agentic platform, called v1. The v1 implementation proves that Claude Code's behavior can be replicated with minimal code (280 lines for the agent loop, 400 for tools), demonstrating that sophistication comes from well-designed tool interfaces and prompts rather than complex agent logic. The v1 implementation should NOT be referred to when building new code, unless the user specifically asks for a comparison to v1.

- **v1 (subdirectory)**: Original implementation demonstrating Claude Code's core mechanics
- `v1/ARCHITECTURE.md`: Architecture of the v1 implementation
- `v1/README.md`: Usage and implementation details for v1
