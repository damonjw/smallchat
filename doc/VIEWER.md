# Multi-Agent Event Log Viewer

## Overview

A single-page, standalone HTML application for viewing and exploring `.jsonl` event logs from multi-agent sessions. The viewer enables visual exploration of agent hierarchies and their conversations through an interactive drag-and-drop interface.

## Log Format

The viewer consumes `.jsonl` log files produced by the session logging system (see `session.py`). Each line is a JSON object representing an event with the following types:

- **`agent_created`**: Records agent creation with `{agent, parent, name, language_model, cause}`
- **`transcript_entry`**: Records messages in agent transcripts with `{agent, role, content, tool_calls, substance, cause}`
- **`fragment`**: Records text produced by an agent but not in its transcript `{agent, content, cause}`

Key fields:
- `message_id`: Unique identifier for each logged item
- `agent`: The agent ID (string) this event relates to
- `parent`: For `agent_created` events, the parent agent ID
- `substance`: References a `message_id` if this content is substantially the same as another message
- `cause`: References `message_id`(s) that were processed to produce this content
- `role`: For transcript entries, one of `user`, `assistant`, or `tool`

## User Interface

### File Loading

1. User opens the HTML file by double-clicking it
2. The page displays a drop target prompting the user to drag a `.jsonl` log file
3. Once a file is dropped, the page displays the log contents
4. To view a different file, the user opens a new browser tab/window with the HTML file

### Layout

The interface is divided into two main sections:

#### Top Section: Agent Hierarchy

Displays the tree structure of agents based on the `parent` field from `agent_created` events. This shows which agents created which subagents, forming a hierarchical tree view.

#### Bottom Section: Chat Panels

One or more panels arranged horizontally, each displaying conversations for one or more selected agents.

**Initial state**: One chat panel displaying the interlocutor agent (the first agent whose parent is `user`).

### Drag and Drop Interactions

Users can manipulate which agents are displayed in which panels:

1. **Add agent to existing panel**: Drag an agent from the hierarchy onto an existing panel → adds that agent to the panel
2. **Create new panel**: Drag an agent from the hierarchy onto the space to the right of an existing panel → creates a new panel with that agent
3. **Remove agent from panel**: Drag an agent out of a panel → removes it from the panel. If the panel becomes empty, it is automatically removed

### Message Display

Each chat panel shows the messages from all agents currently assigned to that panel:

#### Message Types

1. **Inputs** (role=`user`):
   - Displayed in ChatGPT user-input style
   - All inputs to any agent in the panel are shown this way

2. **Utterances** (role=`assistant` without `tool_calls`):
   - Displayed in ChatGPT assistant-message style
   - Prefixed with `[agent_name]: ` when multiple agents are in the same panel
   - Example: `[researcher]: Based on my analysis, the data shows...`

3. **Tool use** (role=`assistant` with `tool_calls`, or role=`tool`):
   - Not displayed in the chat view (these are internal mechanics)

#### Message Ordering

- Messages are displayed in the order they appear in the log file (by `message_id`)
- When multiple panels are visible, temporal ordering is preserved across all panels
- All panels scroll together to maintain temporal alignment

#### Duplicate Removal

To avoid redundant display when multiple agents receive the same message:

1. **Substance-based deduplication**: If message X exists and a later message has `substance=X`, don't display the later message
2. **Content-based deduplication**: If two messages have identical content but no substance linkage, only show the earlier one

## Visual Style

- **User inputs**: Light background, left-aligned or centered (ChatGPT user message style)
- **Agent utterances**: Light assistant-message background with agent name prefix when needed
- **Panels**: Clear visual separation between panels, arranged horizontally with equal widths
- **Agent hierarchy**: Tree structure with expandable/collapsible nodes showing parent-child relationships

## Technical Requirements

- Single standalone HTML file
- No external dependencies (all CSS and JavaScript inline)
- Client-side only (no server communication)
- Handles large log files efficiently
- Responsive to drag-and-drop operations
