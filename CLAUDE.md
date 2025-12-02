# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This codebase contains an LLM-based agentic assistant as a thought experiment to showcase the mechanisms behind Claude Code. It is NOT a production system and has no users. The project explores complex agentic behaviors through two implementations:

- **v2 (root level)**: New architecture implementing persistent subagents with multi-agent discussions
- **v1 (subdirectory)**: Original implementation demonstrating Claude Code's core mechanics

## Documentation

- `doc/GOALS.md`: Research goals and use cases for multi-agent behaviors
- `doc/PLAN.md`: Detailed architectural roadmap for v2 (hooks, subagents, discussions)
- `v1/ARCHITECTURE.md`: Architecture of the v1 implementation
- `v1/README.md`: Usage and implementation details for v1

## Design Philosophy

This is a **research platform** for exploring agentic behaviors:
- **Simple implementation, complex behavior**: Few primitives (Agent, World) enable sophisticated emergent behaviors
- **Rapid prototyping**: Behaviors can be specified in natural language (system prompts) rather than code
- **Homoiconic design**: Agents can create and modify other agents' prompts and behaviors
- **Not for production**: Focus is on exploration and understanding, not robustness or safety

The v1 implementation proves that Claude Code's behavior can be replicated with minimal code (280 lines for the agent loop, 400 for tools), demonstrating that sophistication comes from well-designed tool interfaces and prompts rather than complex agent logic.

The v2 architecture extends this to enable multi-agent scenarios: debates, resource constraints, steel-man reasoning, long-term memory, event-driven agents, Socratic teaching, and strategic thinking.
