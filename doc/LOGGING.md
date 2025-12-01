# Logging Architecture for Multi-Agent System

## Overview

This document describes the logging architecture for session persistence and multi-perspective analysis of the agent system. The logging system enables two main capabilities:

1. **Session resumption**: Save and restore complete agent state to resume interrupted sessions
2. **Multi-perspective viewing**: Extract different views of agent interactions for analysis (e.g., "show just the dialog", "show Jill's inner thoughts")

## Design Principles

1. **Transcripts ARE the state**: Agent transcripts contain all necessary information to reconstruct system state. No separate state tracking needed.
2. **Event sourcing**: Append-only log of messages as they're added to transcripts
3. **Flat structure**: All messages from all agents in a single event stream, tagged with agent IDs
4. **Minimal abstractions**: Simple core entities that support diverse use cases
5. **Single-threaded**: No concurrency concerns (asyncio for async operations, not parallel execution)
6. **Session as state registry**: The Session object is an event-stream backed reflection of the current multi-agent system state

## Fundamental Entities

### 1. Agents

Each agent has:
- **Unique ID**: `agent_001`, `agent_002`, etc. (allocated by Session)
- **Transcript**: Ordered list of messages
- **Parent relationship**: Explicit via `cause` field in agent_created event (points to the tool call that created this agent)
- **Metadata**: `language_model`, creation context

### 2. Events

The logging system records three primary event types:

#### Transcript Entries
Additions to an agent's transcript:
- User messages (role=user)
- Assistant responses (role=assistant) - utterances or tool calls
- Tool results (role=tool)
- System messages (role=system)

Each transcript entry has:
- **Identity**: `message_id` (globally unique)
- **Agent**: `agent_id` (whose transcript this appears in)
- **Content**: `role`, `content`, `tool_calls`, etc.
- **Substance**: `substance` (optional) - what content does this morally represent?

#### Pieces of Text
Intermediate text generated during tool operation but not part of the parent agent's transcript. Used when a tool generates text that will be delivered to other agents.

**Purpose**: Enables deduplication and tool-agnostic viewing. When the same text is delivered to multiple agents, it's stored once as a `piece_of_text`, and each recipient's transcript entry points to it via `substance`.

Each piece of text has:
- **Identity**: `message_id` (globally unique)
- **Agent**: `agent_id` (which agent created this text)
- **Content**: `content` (the text itself)
- **Causation**: `cause` (points to the tool call that generated it)

**Key distinction**: A `piece_of_text` is NOT added to any agent's transcript. It's an intermediate artifact that will be delivered to agents, who log their own transcript entries with `substance` pointing to the piece of text.

#### Agent Creation
Records when a new agent is created in the system.

Each agent creation event has:
- **Identity**: `message_id` (globally unique)
- **Agent**: `agent_id` (the new agent's ID)
- **Causation**: `cause` (optional - points to the tool call that created this agent; omitted for root agent)
- **Metadata**: `name` (optional human-readable name), `language_model`

### 3. Global ID Space

All events (transcript entries, pieces of text, agent creation) share a single global ID space. This allows any event to reference any other event.

### 4. Utterances

An **utterance** is a transcript entry with role=assistant that has `content` but no `tool_calls`. It represents an agent communicating rather than taking actions.

**Identifying utterances**: Filter for `event_type=="transcript_entry"`, `role=="assistant"`, has `content`, no `tool_calls`.

When utterances are communicated to other agents:
1. The original utterance is a transcript entry in the speaker's transcript
2. The recipient receives a (possibly formatted) version with `substance` pointing to the original utterance
3. Hook modifications are visible by comparing the original content with what was received

**Example**: Jack says "Hello" to Jill (direct):
1. `msg_001`: transcript_entry (Jack's assistant message: "Hello")
2. `msg_002`: transcript_entry (Jill's user message: "[Jack]: Hello", substance=msg_001)

The `substance` link shows that Jill's message represents Jack's original utterance, even though the string is formatted differently.

### 5. Responsibility Model

**Session manages state:**
- Allocates unique agent IDs
- Logs all events to the event stream
- Maintains registry of all agents (in-memory and revivifiable)
- Can reconstruct any agent's state from the event stream

**Agents log their own transcript entries:**
- `Agent.response()` logs assistant messages via `session.log_transcript_entry()` and returns a `LoggedString` with its `message_id`
- `Agent.harken(input)` logs user messages, extracting `message_id` from the input if present (used as `substance`)

**LoggedString - logging metadata carrier:**
- A string subclass that carries its message_id without changing operational APIs
- Has `message_id` attribute identifying the substance of this content
  - For originals: their own message_id from the log
  - For formatted versions: the original content's message_id
- Operational code treats it as a regular string
- Logging code extracts metadata via `getattr(input, 'message_id', None)`

**Substance tracking:**
- When an agent delivers a formatted message, the LoggedString's `message_id` points to the original content
- This becomes the `substance` field when logging the recipient's transcript entry
- Example: Jack's utterance (msg_001) → formatted as "[Jack]: Hello" with message_id=msg_001 → Jill's receipt (msg_003, substance=msg_001)

### 6. Causality and Substance Identity

The log records objective facts about what happened. Relationships are captured through explicit links and temporal ordering:

**Transcript entries**:
- Each entry records what enters an agent's transcript
- `substance` field (optional) identifies what content this morally represents
  - If omitted, the entry represents itself (new, original content)
  - If present, points to the original content this is based on
- Tool results have `tool_call_id` linking to originating tool call
- Temporal ordering shows when events occurred

**Pieces of text**:
- `cause` field links to the tool call that created this text
- `agent_id` field identifies which agent created this text
- Represents intermediate content during tool operation
- **Note**: piece_of_text events have `cause`, not `substance` (they are new content caused by a tool call)
- **Note**: `cause` can be a list to allow for tool results that compile multiple messages

**Agent creation events**:
- `cause` field explicitly links to the tool call that created this agent
- No need for temporal inference or name matching
- Makes parent-child relationships explicit and unambiguous

**Information flow example:**
```
msg_001: transcript_entry (Jack: "Hello")                    [Jack's assistant message]
msg_002: transcript_entry (Jill: "[Jack]: Hello")           [Jill's user message, substance=msg_001]
```

The `substance` link shows that Jill's message represents the same content as Jack's utterance (morally the same, though string is formatted). Hook interventions are visible by comparing content: msg_001 vs msg_002.

### 7. Why Session is Necessary

The Session class is essential for correctness, not just convenience. Consider this scenario:

1. Main agent creates subagent Jack (`agent_002`)
2. Jack terminates (removed from agent tree)
3. Session saved and process exits
4. Session resumed
5. Main agent creates new subagent Jill

Without Session managing agent IDs, Jill might be allocated `agent_002` again (if agent ID counter wasn't restored), causing ID collision with the terminated Jack in the event log. This would corrupt the viewer's understanding of which events belong to which agent.

Session prevents this by:
- **Owning both message_counter and agent_counter**: Both restored atomically from the event stream
- **Maintaining agent registry**: Knows about all agents that have ever existed
- **Single restoration path**: Impossible to resume session without restoring both counters

This ensures the event stream remains an unambiguous, consistent record across session resumptions.

## Log Format

### Event Stream Structure

Append-only JSONL file where each line is an event:

```jsonl
{"message_id": "msg_001", "event_type": "agent_created", "agent_id": "agent_root", "language_model": "anthropic/claude-sonnet-4-5-20250929"}
{"message_id": "msg_002", "event_type": "transcript_entry", "agent_id": "agent_root", "role": "user", "content": "Create Jack and Jill"}
{"message_id": "msg_003", "event_type": "transcript_entry", "agent_id": "agent_root", "role": "assistant", "tool_calls": [...]}
{"message_id": "msg_004", "event_type": "agent_created", "agent_id": "agent_jack", "name": "Jack", "language_model": "anthropic/claude-sonnet-4-5-20250929"}
{"message_id": "msg_005", "event_type": "transcript_entry", "agent_id": "agent_jack", "role": "assistant", "content": "Hi"}
```

### Event Schemas

#### Transcript Entry Event

**Core fields:**
```json
{
  "message_id": "msg_123",
  "event_type": "transcript_entry",
  "agent_id": "agent_001",
  "role": "user|assistant|tool|system",
  "content": "..."
}
```

**Substance (optional):**
```json
{
  "substance": "msg_100"  // Points to the content this morally represents
}
```

**When to include**: Add `substance` when this entry represents content from another message (e.g., formatted version of an utterance). If omitted, the entry represents itself (new, original content).

**Tool calls (for role=assistant):**
```json
{
  "tool_calls": [
    {
      "id": "call_abc",
      "type": "function",
      "function": {"name": "task", "arguments": "{...}"}
    }
  ]
}
```

**Tool results (for role=tool):**
```json
{
  "tool_call_id": "call_abc",
  "name": "task"
}
```

#### Piece of Text Event

**Core fields:**
```json
{
  "message_id": "msg_124",
  "event_type": "piece_of_text",
  "agent_id": "agent_001",
  "content": "You meet in a cafe. Introduce yourselves.",
  "cause": "msg_123"
}
```

**Fields:**
- `agent_id`: Which agent created this text
- `cause`: Points to the tool call that generated this text (can be a list for tool results compiling multiple messages)

**When to use**: Create a `piece_of_text` when a tool generates text that will be delivered to multiple agents (e.g., broadcast prompt from parent). The same `piece_of_text` can be referenced by multiple transcript entries via their `substance` field.

**Note**: For formatted utterances (e.g., "[Jack]: Hello"), do NOT create a piece_of_text. Instead, deliver the formatted message with `substance` pointing to the original utterance. Only create piece_of_text for content generated by the parent agent.

#### Agent Creation Event

```json
{
  "message_id": "msg_004",
  "event_type": "agent_created",
  "agent_id": "agent_002",
  "cause": "msg_003",
  "name": "Jack",
  "language_model": "anthropic/claude-sonnet-4-5-20250929"
}
```

**Fields:**
- `cause`: Points to the tool call message that created this agent (explicit parent-child relationship). Omitted for root agent.
- `name`: Optional human-readable name for the agent
- `language_model`: The model used by this agent

This explicit relationship avoids the need for temporal inference or name matching. The root agent will not have a cause field.

## Concrete Examples

### Example 1: Jack and Jill Discussion

```jsonl
{"message_id": "msg_001", "event_type": "agent_created", "agent_id": "agent_root", "language_model": "anthropic/claude-sonnet-4-5-20250929"}
{"message_id": "msg_002", "event_type": "transcript_entry", "agent_id": "agent_root", "role": "user", "content": "Create Jack and Jill for a cafe discussion"}
{"message_id": "msg_003", "event_type": "transcript_entry", "agent_id": "agent_root", "role": "assistant", "tool_calls": [{"id": "c1", "function": {"name": "task", "arguments": "{\"name\": \"Jack\", \"system_prompt\": \"You work in HR...\"}"}}]}
{"message_id": "msg_004", "event_type": "agent_created", "agent_id": "agent_jack", "cause": "msg_003", "name": "Jack", "language_model": "anthropic/claude-sonnet-4-5-20250929"}
{"message_id": "msg_005", "event_type": "transcript_entry", "agent_id": "agent_jack", "role": "system", "content": "You work in HR..."}
{"message_id": "msg_006", "event_type": "transcript_entry", "agent_id": "agent_root", "role": "tool", "tool_call_id": "c1", "content": "Created subagent: Jack"}
{"message_id": "msg_007", "event_type": "transcript_entry", "agent_id": "agent_root", "role": "assistant", "tool_calls": [{"id": "c2", "function": {"name": "task", "arguments": "{\"name\": \"Jill\", \"system_prompt\": \"You are an aspiring author...\"}"}}]}
{"message_id": "msg_008", "event_type": "agent_created", "agent_id": "agent_jill", "cause": "msg_007", "name": "Jill", "language_model": "anthropic/claude-sonnet-4-5-20250929"}
{"message_id": "msg_009", "event_type": "transcript_entry", "agent_id": "agent_jill", "role": "system", "content": "You are an aspiring author..."}
{"message_id": "msg_010", "event_type": "transcript_entry", "agent_id": "agent_root", "role": "tool", "tool_call_id": "c2", "content": "Created subagent: Jill"}
{"message_id": "msg_011", "event_type": "transcript_entry", "agent_id": "agent_root", "role": "assistant", "tool_calls": [{"id": "c3", "function": {"name": "discuss", "arguments": "{\"prompt\": \"You meet in a cafe. Introduce yourselves.\", \"speakers\": [\"Jack\", \"Jill\"]}"}}]}
{"message_id": "msg_012", "event_type": "piece_of_text", "agent_id": "agent_root", "content": "You meet in a cafe. Introduce yourselves.", "cause": "msg_011"}
{"message_id": "msg_013", "event_type": "transcript_entry", "agent_id": "agent_jack", "role": "user", "content": "You meet in a cafe. Introduce yourselves.", "substance": "msg_012"}
{"message_id": "msg_014", "event_type": "transcript_entry", "agent_id": "agent_jill", "role": "user", "content": "You meet in a cafe. Introduce yourselves.", "substance": "msg_012"}
{"message_id": "msg_015", "event_type": "transcript_entry", "agent_id": "agent_jack", "role": "assistant", "content": "Hi, I'm Jack. *extends hand*"}
{"message_id": "msg_016", "event_type": "transcript_entry", "agent_id": "agent_root", "role": "tool", "tool_call_id": "c3", "content": "Hi, I'm Jack. *extends hand*"}
{"message_id": "msg_017", "event_type": "transcript_entry", "agent_id": "agent_jill", "role": "user", "content": "[Jack]: Hi, I'm Jack. *extends hand*", "substance": "msg_015"}
{"message_id": "msg_018", "event_type": "transcript_entry", "agent_id": "agent_jill", "role": "assistant", "content": "*smiles* Hello Jack, I'm Jill."}
{"message_id": "msg_019", "event_type": "transcript_entry", "agent_id": "agent_root", "role": "tool", "tool_call_id": "c3", "content": "*smiles* Hello Jack, I'm Jill."}
{"message_id": "msg_020", "event_type": "transcript_entry", "agent_id": "agent_jack", "role": "user", "content": "[Jill]: *smiles* Hello Jack, I'm Jill.", "substance": "msg_018"}
```

Note: The initial prompt (msg_012) is a `piece_of_text` created by the discuss tool (with `cause`=msg_011). Both Jack and Jill receive it (msg_013, msg_014 both have substance=msg_012). When Jack speaks (msg_015), his utterance is formatted as "[Jack]: ..." and delivered to Jill (msg_017) with substance=msg_015. No piece_of_text is created for the formatted utterance - it's just a formatted version of the original, so substance points directly to Jack's utterance.

### Example 2: Inner Monologue

```jsonl
{"message_id": "msg_030", "event_type": "transcript_entry", "agent_id": "agent_jill", "role": "assistant", "tool_calls": [{"id": "c4", "function": {"name": "task", "arguments": "{\"name\": \"Inner\", \"system_prompt\": \"You are Jill's inner voice...\"}"}}]}
{"message_id": "msg_031", "event_type": "agent_created", "agent_id": "agent_jill_inner", "cause": "msg_030", "name": "Inner", "language_model": "anthropic/claude-sonnet-4-5-20250929"}
{"message_id": "msg_032", "event_type": "transcript_entry", "agent_id": "agent_jill_inner", "role": "system", "content": "You are Jill's inner voice..."}
{"message_id": "msg_033", "event_type": "transcript_entry", "agent_id": "agent_jill", "role": "user", "content": "[Jack]: Hi, I'm Jack. *extends hand*", "substance": "msg_015"}
{"message_id": "msg_034", "event_type": "transcript_entry", "agent_id": "agent_jill", "role": "assistant", "tool_calls": [{"id": "c5", "function": {"name": "discuss", "arguments": "{\"speakers\": [\"Inner\"], \"prompt\": \"Jack just introduced himself. What should I say?\"}"}}]}
{"message_id": "msg_035", "event_type": "piece_of_text", "agent_id": "agent_jill", "content": "Jack just introduced himself. What should I say?", "cause": "msg_034"}
{"message_id": "msg_036", "event_type": "transcript_entry", "agent_id": "agent_jill_inner", "role": "user", "content": "Jack just introduced himself. What should I say?", "substance": "msg_035"}
{"message_id": "msg_037", "event_type": "transcript_entry", "agent_id": "agent_jill_inner", "role": "assistant", "content": "Be friendly but not over-eager. A simple greeting with a smile."}
{"message_id": "msg_038", "event_type": "transcript_entry", "agent_id": "agent_jill", "role": "tool", "tool_call_id": "c5", "content": "Be friendly but not over-eager. A simple greeting with a smile."}
{"message_id": "msg_039", "event_type": "transcript_entry", "agent_id": "agent_jill", "role": "assistant", "content": "*smiles* Hello Jack, I'm Jill."}
```

Note: Jill receives Jack's message (msg_033) with substance pointing to Jack's original utterance (msg_015). Inner's response (msg_037) is only sent to Jill (msg_038), not to Jack. The selective information flow is evident from which agents' transcripts contain which messages.

### Example 3: Hook Intervention (Resource Constraints)

```jsonl
{"message_id": "msg_100", "event_type": "transcript_entry", "agent_id": "agent_root", "role": "assistant", "tool_calls": [{"id": "c9", "function": {"name": "task", "arguments": "{\"name\": \"ResourceMonitor\", \"system_prompt\": \"Monitor resource usage...\"}"}}]}
{"message_id": "msg_101", "event_type": "agent_created", "agent_id": "agent_resource_hook", "cause": "msg_100", "name": "ResourceMonitor", "language_model": "anthropic/claude-sonnet-4-5-20250929"}
{"message_id": "msg_102", "event_type": "transcript_entry", "agent_id": "agent_root", "role": "assistant", "tool_calls": [{"id": "c10", "function": {"name": "task", "arguments": "{\"name\": \"Searcher4\"}"}}]}
{"message_id": "msg_103", "event_type": "transcript_entry", "agent_id": "agent_resource_hook", "role": "user", "content": "Agent 'agent_root' is attempting to create subagent 'Searcher4'. Current subagent count: 3. Approve?"}
{"message_id": "msg_104", "event_type": "transcript_entry", "agent_id": "agent_resource_hook", "role": "assistant", "content": "DENY. Maximum subagents (3) already reached."}
{"message_id": "msg_105", "event_type": "transcript_entry", "agent_id": "agent_root", "role": "tool", "tool_call_id": "c10", "content": "Error: Action blocked by hook 'ResourceMonitor': Maximum subagents (3) already reached."}
```

Note: The hook agent receives a prompt (msg_103) asking for approval, responds with a denial (msg_104), and the denial appears as an error in the tool result (msg_105).

### Example 4: External Trigger (Event-Driven)

```jsonl
{"message_id": "msg_200", "event_type": "transcript_entry", "agent_id": "agent_watcher", "role": "user", "content": "File changed: data.json"}
{"message_id": "msg_201", "event_type": "transcript_entry", "agent_id": "agent_watcher", "role": "assistant", "content": "I'll reload the data and notify the main agent."}
```

Note: External events appear as user messages in the agent's transcript, fitting naturally into the same model as agent-to-agent communication.

## Public API Specifications

### LoggedString Class

```python
class LoggedString(str):
    """A string with its message_id for logging.

    During execution, content identity is implicit in the call stack. This class
    externalizes that runtime information for logging without changing APIs.

    Attributes:
        message_id: The message_id identifying the substance of this content.
            - For originals: their own message_id in the log
            - For formatted versions: the original content's message_id
    """

    def __new__(cls, content, message_id=None):
        """Create a LoggedString with optional message_id metadata.

        Args:
            content: The string content
            message_id: Optional message_id for substance tracking

        Returns:
            LoggedString instance that behaves as a normal string
        """
```

### Session Class

```python
class Session:
    """Event-stream backed representation of multi-agent system state.

    The Session maintains the authoritative registry of all agents and can revivify
    any agent from the event stream on demand. It manages both message_id and
    agent_id allocation, ensuring unique IDs across session resumptions.

    This class is necessary for correctness: without it, agent IDs could collide
    when resuming sessions where agents have been created and terminated.
    """

    @staticmethod
    def load(session_file):
        """Load existing session and restore all state from event stream.

        Reads the event stream once to extract:
        - Maximum message_id (to restore message counter)
        - Maximum agent_id (to restore agent counter)
        - Metadata for all agents that exist/existed

        Args:
            session_file: Path to JSONL session file

        Returns:
            Session instance with counters and metadata restored
        """

    def allocate_agent_id(self):
        """Allocate a new unique agent ID.

        Called by Agent.__init__ to get a unique ID.

        Returns:
            Unique agent_id (e.g., "agent_003")
        """

    def log_agent_created(self, agent_id, cause=None, name=None, language_model=None):
        """Log agent creation event.

        Called by tool code after creating an agent (not by Agent.__init__).
        Only the parent/tool knows the cause and name context.

        Args:
            agent_id: The unique ID for this agent
            cause: message_id of tool call that created this (None for root)
            name: Optional human-readable name
            language_model: The model this agent uses

        Returns:
            message_id of the logged event
        """

    def log_transcript_entry(self, agent_id, message, substance=None):
        """Log a transcript entry event.

        Called by Agent.harken() and Agent.response() to log messages.

        Args:
            agent_id: The agent whose transcript this appears in
            message: The message dict (role, content, tool_calls, etc.)
            substance: Optional - what content does this morally represent?
                      (omit if this entry represents itself - new, original content)

        Returns:
            message_id of the logged event
        """

    def log_piece_of_text(self, agent_id, content, cause):
        """Log a piece of text event.

        Called by tools that generate content for broadcast to multiple agents.

        Args:
            agent_id: The agent that created this text
            content: The text content
            cause: message_id of the tool call that generated this (can be a list)

        Returns:
            message_id of the logged event
        """
```

### load_session Function

```python
def load_session(session_file):
    """Load session and reconstruct agent tree.

    For new sessions: Creates root agent and empty Session
    For existing sessions: Loads Session with restored counters and metadata,
                          then reconstructs the full agent tree from event stream

    Args:
        session_file: Path to JSONL session file

    Returns:
        Tuple of (root_agent, session)
        - root_agent: The root agent with full tree of subagents loaded
        - session: Session instance with all state restored
    """
```

### Agent Class Interface

```python
class Agent:
    """An LLM-powered agent with transcript and subagents.

    Agents require a Session for ID allocation and logging.
    """

    def __init__(self, session, system_prompt=None, init_prompt=None):
        """Create agent with required session.

        The agent allocates its ID from the session. The parent/tool is responsible
        for calling session.log_agent_created() with the cause and name context.

        Args:
            session: Session for ID allocation and logging (required)
            system_prompt: Optional system prompt
            init_prompt: Optional initial transcript (for resumption)
        """

    def harken(self, input):
        """Add a user message to transcript.

        Extracts message_id from input if it's a LoggedString,
        and logs it as the substance field via session.log_transcript_entry().

        Args:
            input: The message content (may be LoggedString with metadata)
        """

    async def response(self):
        """Generate response and log it.

        Logs the response via session.log_transcript_entry() and returns
        a LoggedString carrying the message_id.

        Returns:
            LoggedString with message_id pointing to itself (original content)
        """

    def inform(self, dst, txt):
        """Send a message from this agent to another agent.

        Args:
            dst: The destination Agent object
            txt: The text message (may be LoggedString with metadata)
        """
```

### SessionViewer Class

```python
class SessionViewer:
    """Viewer for extracting different perspectives from session logs.

    Provides tool-agnostic views of agent interactions by following
    substance and cause links in the event stream.
    """

    def __init__(self, session_file):
        """Load session events for viewing.

        Args:
            session_file: Path to JSONL session file
        """

    def list_agents(self):
        """List all agents in the session.

        Returns:
            Dict mapping agent_id to name
        """

    def get_transcript(self, agent_id):
        """Get all transcript_entry events for a specific agent.

        Args:
            agent_id: The agent whose transcript to retrieve

        Returns:
            List of transcript_entry event dicts
        """

    def extract_dialog(self, agent_ids):
        """Extract distinct messages exchanged between selected agents.

        Uses substance to identify when multiple agents received the same message,
        showing each distinct piece of content only once.

        Args:
            agent_ids: List of agent IDs to include in dialog

        Returns:
            List of distinct messages (deduplicated by substance)
        """

    def extract_agent_perspective(self, agent_id):
        """Show what an agent heard, thought, and said.

        Args:
            agent_id: The agent whose perspective to extract

        Returns:
            Formatted string showing agent's perspective
        """

    def build_causality_index(self):
        """Build an index of causal relationships.

        Returns:
            Dict mapping message_id -> parent_message_id
        """

    def trace_message_flow(self, message_id):
        """Follow a message's causality chain.

        Args:
            message_id: Starting message to trace

        Returns:
            List of events in causality chain (oldest to newest)
        """

    def trace_content_references(self, content_msg_id):
        """Find all messages that represent this content.

        Finds all transcript_entry events that have this message_id
        as their substance field.

        Args:
            content_msg_id: The message_id to find references to

        Returns:
            List of transcript_entry events referencing this content
        """
```

## Justification: Why This Design Works

### 1. Session is Necessary for Correctness

The Session class guarantees unique agent IDs across session resumptions:

**Problem without Session:**
- Agent IDs managed by `Agent._next_id` class variable
- message IDs managed by separate SessionLogger
- If session resumed incorrectly, agent_counter might not be restored
- New agent could get same ID as terminated agent in log → ID collision

**Solution with Session:**
- Session owns both message_counter and agent_counter
- Both restored atomically in `Session.load()`
- Single restoration path - impossible to get out of sync
- Agent registry tracks all agents (prevents collisions)

### 2. Supports Session Resumption

**Complete state reconstruction:**
- `transcript_entry` events contain every message added to every transcript
- Agent creation events track the agent tree structure via explicit `cause` links
- Replaying transcript_entry events rebuilds exact agent state
- Session.load() restores all counters and metadata in single pass

**Resume points:**
- After each `Agent.response()` completes (before next user input)
- No mid-tool-use resumption needed (avoids complexity)
- Simple single-pass replay of transcript_entry events

### 3. Substance and Causation

**The `substance` field:**
- Identifies what content a message morally represents
- For originals: omitted (the message represents itself - new content)
- For formatted versions: points to the original content
- Enables deduplication without string matching
- Identifies when multiple agents received the same content

**The `cause` field:**
- Links new content to what triggered its creation
- Used in `piece_of_text` events to link to the tool call that generated the text
- Used in `agent_created` events to link to the tool call that created the agent
- Can be a list for tool results that compile multiple messages
- **Mutual exclusivity**: Events have either `substance` (same content as something else) OR `cause` (new content triggered by something), never both

**Hook transparency example:**
```
msg_001: transcript_entry (Jack says "password: 1234")
msg_002: transcript_entry (Jill hears "password: [REDACTED]", substance=msg_001)
```
Hook intervention visible by comparing msg_001 content (original) vs msg_002 content (what Jill received). Both have the same substance, showing they morally represent the same message.

### 4. Enables Multi-Perspective Viewing

**Jack and Jill dialog:**
- Collect transcript entries for selected agents (Jack, Jill)
- Group by `substance` to identify duplicate content
- Show each distinct piece of content once
- Tool-agnostic: viewer doesn't parse tool arguments, just follows substance links

**Jill's inner monologue:**
- Filter transcript_entry with `agent_id == "agent_jill"` or `agent_id == "agent_jill_inner"`
- Shows what Jill heard, her inner thoughts, and what she said

**Information flow analysis:**
- Trace `substance` links to find original content
- Find all messages representing the same content using `trace_content_references()`
- See who heard what by checking which agents have transcript entries with substance pointing to the same message
- No string matching needed - content identity is explicit

### 5. Agent Registry Enables Revivification

The Session maintains a registry of all agents, enabling:

**Revivification:**
- Any agent can be reconstructed from event stream
- Useful for agents that were terminated or evicted from memory
- Session scans log for all transcript_entry events with matching agent_id
- Rebuilds agent with full transcript restored

**Memory management:**
- Can evict agents from memory to save resources
- Revivify on demand when needed
- Supports long sessions with many transient agents

**State inspection:**
- `list_agents()` shows all agents that exist/existed
- Can query agent metadata without loading full state
- Supports debugging and analysis

### 6. Tool Agnosticism

**Complete tool agnosticism:**
- Tools create `piece_of_text` events for parent-generated broadcasts
- Recipient transcript entries have `substance` pointing to the piece_of_text or original utterance
- Viewer groups by `substance` to identify shared messages
- No knowledge of discuss, broadcast, whisper, translation, or any tool specifics
- Logging infrastructure never changes as new tools are added

The viewer doesn't need to know if a message was from discuss, broadcast, or any other tool. It just follows `substance` links.

### 7. Clean Responsibility Model

**Session responsibilities:**
- Allocate unique IDs (messages and agents)
- Log all events to event stream
- Maintain agent registry
- Revivify agents on demand

**Agent responsibilities:**
- Maintain transcript
- Generate responses
- Call session.log_transcript_entry() to log

**LoggedString responsibilities:**
- Carry message_id metadata invisibly
- Enable clean separation: operational code unaware of logging

**Separation of concerns:**
- Operational code: `harken(input)` - clean signature, no logging parameters
- Logging code: `getattr(input, 'message_id', None)` - extracts metadata at boundaries
- Session manages all state and logging
- Agents focus on LLM interaction

## Summary

This logging architecture achieves:
- **Correctness**: Session guarantees unique IDs across resumptions
- **Completeness**: Can resume sessions with full state
- **Flexibility**: Supports unknown future analyses
- **Simplicity**: Minimal event types (transcript_entry, piece_of_text, agent_created)
- **Transparency**: Hook interventions visible via substance links
- **Tool agnosticism**: Viewer never parses tool arguments
- **Clean separation**: Logging doesn't pollute operational code

**Key insights:**
1. **Session is necessary** - Not just convenient, but required for correctness
2. **Transcripts are the state** - Agent state captured entirely in transcript_entry events
3. **LoggedString separates concerns** - Logging metadata travels invisibly
4. **substance vs cause** - Clear distinction between same content and triggered content
5. **Mutual exclusivity** - Events have substance OR cause, never both
6. **Registry enables revivification** - Any agent can be reconstructed on demand
