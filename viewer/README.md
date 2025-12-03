# Multi-Agent Event Log Viewer

## Current Architecture

The viewer is a single-page Svelte application that compiles to a standalone HTML file (46.66 kB, gzip: 17.88 kB).

### Component Structure
- **App.svelte**: Main component with file drag-and-drop
- **AgentHierarchy.svelte**: Displays agent tree
- **AgentNode.svelte**: Recursive tree node with inline single-child chains
- **ChatPanels.svelte**: Unified scroll container with panel headers and message grid
- **Message.svelte**: Individual message display

### State Management (stores.js)
- `agents`: Map of agent_id → {id, name, parent, children[]}
- `allMessages`: Array of all parsed messages
- `panels`: Array of {id, agentIds[]} for each chat panel
- `interlocutor`: Derived store for the top-level agent

### Parsing (logParser.js)
- `parseLog(text)`: Parses entire .jsonl file, builds agent tree, extracts messages
- `deduplicateMessages(messages)`: Removes duplicates based on substance and content
- Only includes:
  - User messages (inputs): `role === 'user'`
  - Assistant messages without tool calls (utterances): `role === 'assistant' && !tool_calls`

### Current Behavior
1. User drags .jsonl file onto drop zone
2. File is read entirely as text via `file.text()`
3. Entire log is parsed in one pass
4. Agents and messages populate stores
5. UI renders based on store state

