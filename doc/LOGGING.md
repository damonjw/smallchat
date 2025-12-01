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

## Fundamental Entities

### 1. Agents

Each agent has:
- **Unique ID**: `agent_001`, `agent_002`, etc.
- **Transcript**: Ordered list of messages
- **Parent relationship**: Inferred from temporal ordering (agent creation event appears between parent's tool call and tool result, with matching name)
- **Metadata**: `language_model`, creation context

### 2. Events

The logging system records two primary event types:

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
- **Content identity**: `content_id` (optional) - what content does this morally represent?

#### Pieces of Text
Intermediate text generated during tool operation but not part of the parent agent's transcript. Used when a tool generates text that will be delivered to other agents.

**Purpose**: Enables deduplication and tool-agnostic viewing. When the same text is delivered to multiple agents, it's stored once as a `piece_of_text`, and each recipient's transcript entry points to it via `content_id`.

Each piece of text has:
- **Identity**: `message_id` (globally unique)
- **Content**: `content` (the text itself)
- **Generation tracking**: `caused_by` (typically points to the tool call that generated it)

**Key distinction**: A `piece_of_text` is NOT added to any agent's transcript. It's an intermediate artifact that will be delivered to agents, who log their own transcript entries with `content_id` pointing to the piece of text.

### 3. Global ID Space

All events (transcript entries, pieces of text, agent creation) share a single global ID space. This allows any event to reference any other event.

### 4. Utterances

An **utterance** is a transcript entry with role=assistant that has `content` but no `tool_calls`. It represents an agent communicating rather than taking actions.

**Identifying utterances**: Filter for `event_type=="transcript_entry"`, `role=="assistant"`, has `content`, no `tool_calls`.

When utterances are communicated to other agents:
1. The original utterance is a transcript entry in the speaker's transcript
2. The recipient receives a (possibly formatted) version with `content_id` pointing to the original utterance
3. Hook modifications are visible by comparing the original content with what was received

**Example**: Jack says "Hello" to Jill (direct):
1. `msg_001`: transcript_entry (Jack's assistant message: "Hello")
2. `msg_002`: transcript_entry (Jill's user message: "[Jack]: Hello", content_id=msg_001)

The `content_id` link shows that Jill's message represents Jack's original utterance, even though the string is formatted differently.

### 5. Responsibility Model

**Agents log their own transcript entries:**
- `Agent.response()` logs assistant messages and returns a `MessageString` with `content_id`
- `Agent.harken(input)` logs user messages, extracting `content_id` from the input if present

**MessageString - logging metadata carrier:**
- A string subclass that carries logging metadata without changing operational APIs
- Has `content_id` attribute (what content does this morally represent?)
  - For originals: their own message_id in the log
  - For formatted versions: the original content's message_id
- Has `caused_by` attribute (only for piece_of_text - which tool call created this)
- Operational code treats it as a regular string
- Logging code extracts metadata via `getattr(input, 'content_id', None)`

**Content identity tracking:**
- When an agent delivers a formatted message, the `content_id` points to the original content
- This enables viewer to deduplicate without string matching
- Example: Jack's utterance (msg_001) → formatted as "[Jack]: Hello" with content_id=msg_001 → Jill's receipt (msg_003, content_id=msg_001)

### 6. Causality and Content Identity

The log records objective facts about what happened. Causal relationships are captured through explicit links and temporal ordering:

**Transcript entries**:
- Each entry records what enters an agent's transcript
- `content_id` field (optional) identifies what content this morally represents
  - If omitted, the entry represents itself (content_id = message_id implicitly)
  - If present, points to the original content this is based on
- Tool results have `tool_call_id` linking to originating tool call
- Temporal ordering shows when events occurred

**Pieces of text**:
- `caused_by` field links to the tool call that created this text
- Represents intermediate content during tool operation

**Agent creation events**:
- Temporal ordering places creation between parent's tool call and tool result
- The `name` field matches the tool call arguments
- Viewer parses tool call arguments to match creation events with originating tool calls

**Information flow example:**
```
msg_001: transcript_entry (Jack: "Hello")                    [Jack's assistant message]
msg_002: transcript_entry (Jill: "[Jack]: Hello")           [Jill's user message, content_id=msg_001]
```

The `content_id` link shows that Jill's message represents the same content as Jack's utterance (morally the same, though string is formatted). Hook interventions are visible by comparing content: msg_001 vs msg_002.

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

**Content identity (optional):**
```json
{
  "content_id": "msg_100"  // Points to the content this morally represents
}
```

**When to include**: Add `content_id` when this entry represents content from another message (e.g., formatted version of an utterance). If omitted, the entry represents itself.

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
  "content": "You meet in a cafe. Introduce yourselves."
}
```

**Generation tracking (typically present):**
```json
{
  "caused_by": "msg_123"  // Points to the tool call that generated this text
}
```

**When to use**: Create a `piece_of_text` when a tool generates text that will be delivered to multiple agents (e.g., broadcast prompt from parent). The same `piece_of_text` can be referenced by multiple transcript entries via their `content_id` field.

**Note**: For formatted utterances (e.g., "[Jack]: Hello"), do NOT create a piece_of_text. Instead, deliver the formatted message with `content_id` pointing to the original utterance. Only create piece_of_text for content generated by the parent agent.

#### Agent Creation Event

```json
{
  "message_id": "msg_004",
  "event_type": "agent_created",
  "agent_id": "agent_002",
  "name": "Jack",
  "language_model": "anthropic/claude-sonnet-4-5-20250929"
}
```

The parent agent is inferred from temporal ordering: the creation event appears between the parent's tool call (to the `task` function) and the corresponding tool result. The `name` field matches the name in the tool call arguments, allowing the viewer to link creation events to their originating tool calls when multiple agents are created concurrently.

## Concrete Examples

### Example 1: Jack and Jill Discussion

```jsonl
{"message_id": "msg_001", "event_type": "agent_created", "agent_id": "agent_root", "language_model": "anthropic/claude-sonnet-4-5-20250929"}
{"message_id": "msg_002", "event_type": "transcript_entry", "agent_id": "agent_root", "role": "user", "content": "Create Jack and Jill for a cafe discussion"}
{"message_id": "msg_003", "event_type": "transcript_entry", "agent_id": "agent_root", "role": "assistant", "tool_calls": [{"id": "c1", "function": {"name": "task", "arguments": "{\"name\": \"Jack\", \"system_prompt\": \"You work in HR...\"}"}}]}
{"message_id": "msg_004", "event_type": "agent_created", "agent_id": "agent_jack", "name": "Jack", "language_model": "anthropic/claude-sonnet-4-5-20250929"}
{"message_id": "msg_005", "event_type": "transcript_entry", "agent_id": "agent_jack", "role": "system", "content": "You work in HR..."}
{"message_id": "msg_006", "event_type": "transcript_entry", "agent_id": "agent_root", "role": "tool", "tool_call_id": "c1", "content": "Created subagent: Jack"}
{"message_id": "msg_007", "event_type": "transcript_entry", "agent_id": "agent_root", "role": "assistant", "tool_calls": [{"id": "c2", "function": {"name": "task", "arguments": "{\"name\": \"Jill\", \"system_prompt\": \"You are an aspiring author...\"}"}}]}
{"message_id": "msg_008", "event_type": "agent_created", "agent_id": "agent_jill", "name": "Jill", "language_model": "anthropic/claude-sonnet-4-5-20250929"}
{"message_id": "msg_009", "event_type": "transcript_entry", "agent_id": "agent_jill", "role": "system", "content": "You are an aspiring author..."}
{"message_id": "msg_010", "event_type": "transcript_entry", "agent_id": "agent_root", "role": "tool", "tool_call_id": "c2", "content": "Created subagent: Jill"}
{"message_id": "msg_011", "event_type": "transcript_entry", "agent_id": "agent_root", "role": "assistant", "tool_calls": [{"id": "c3", "function": {"name": "discuss", "arguments": "{\"prompt\": \"You meet in a cafe. Introduce yourselves.\", \"speakers\": [\"Jack\", \"Jill\"]}"}}]}
{"message_id": "msg_012", "event_type": "piece_of_text", "content": "You meet in a cafe. Introduce yourselves.", "caused_by": "msg_011"}
{"message_id": "msg_013", "event_type": "transcript_entry", "agent_id": "agent_jack", "role": "user", "content": "You meet in a cafe. Introduce yourselves.", "content_id": "msg_012"}
{"message_id": "msg_014", "event_type": "transcript_entry", "agent_id": "agent_jill", "role": "user", "content": "You meet in a cafe. Introduce yourselves.", "content_id": "msg_012"}
{"message_id": "msg_015", "event_type": "transcript_entry", "agent_id": "agent_jack", "role": "assistant", "content": "Hi, I'm Jack. *extends hand*"}
{"message_id": "msg_016", "event_type": "transcript_entry", "agent_id": "agent_root", "role": "tool", "tool_call_id": "c3", "content": "Hi, I'm Jack. *extends hand*"}
{"message_id": "msg_017", "event_type": "transcript_entry", "agent_id": "agent_jill", "role": "user", "content": "[Jack]: Hi, I'm Jack. *extends hand*", "content_id": "msg_015"}
{"message_id": "msg_018", "event_type": "transcript_entry", "agent_id": "agent_jill", "role": "assistant", "content": "*smiles* Hello Jack, I'm Jill."}
{"message_id": "msg_019", "event_type": "transcript_entry", "agent_id": "agent_root", "role": "tool", "tool_call_id": "c3", "content": "*smiles* Hello Jack, I'm Jill."}
{"message_id": "msg_020", "event_type": "transcript_entry", "agent_id": "agent_jack", "role": "user", "content": "[Jill]: *smiles* Hello Jack, I'm Jill.", "content_id": "msg_018"}
```

Note: The initial prompt (msg_012) is a `piece_of_text` created by the discuss tool. Both Jack and Jill receive it (msg_013, msg_014 both have content_id=msg_012). When Jack speaks (msg_015), his utterance is formatted as "[Jack]: ..." and delivered to Jill (msg_017) with content_id=msg_015. No piece_of_text is created for the formatted utterance - it's just a formatted version of the original, so content_id points directly to Jack's utterance.

### Example 2: Inner Monologue

```jsonl
{"message_id": "msg_030", "event_type": "transcript_entry", "agent_id": "agent_jill", "role": "assistant", "tool_calls": [{"id": "c4", "function": {"name": "task", "arguments": "{\"name\": \"Inner\", \"system_prompt\": \"You are Jill's inner voice...\"}"}}]}
{"message_id": "msg_031", "event_type": "agent_created", "agent_id": "agent_jill_inner", "name": "Inner", "language_model": "anthropic/claude-sonnet-4-5-20250929"}
{"message_id": "msg_032", "event_type": "transcript_entry", "agent_id": "agent_jill_inner", "role": "system", "content": "You are Jill's inner voice..."}
{"message_id": "msg_033", "event_type": "transcript_entry", "agent_id": "agent_jill", "role": "user", "content": "[Jack]: Hi, I'm Jack. *extends hand*", "content_id": "msg_015"}
{"message_id": "msg_034", "event_type": "transcript_entry", "agent_id": "agent_jill", "role": "assistant", "tool_calls": [{"id": "c5", "function": {"name": "discuss", "arguments": "{\"speakers\": [\"Inner\"], \"prompt\": \"Jack just introduced himself. What should I say?\"}"}}]}
{"message_id": "msg_035", "event_type": "piece_of_text", "content": "Jack just introduced himself. What should I say?", "caused_by": "msg_034"}
{"message_id": "msg_036", "event_type": "transcript_entry", "agent_id": "agent_jill_inner", "role": "user", "content": "Jack just introduced himself. What should I say?", "content_id": "msg_035"}
{"message_id": "msg_037", "event_type": "transcript_entry", "agent_id": "agent_jill_inner", "role": "assistant", "content": "Be friendly but not over-eager. A simple greeting with a smile."}
{"message_id": "msg_038", "event_type": "transcript_entry", "agent_id": "agent_jill", "role": "tool", "tool_call_id": "c5", "content": "Be friendly but not over-eager. A simple greeting with a smile."}
{"message_id": "msg_039", "event_type": "transcript_entry", "agent_id": "agent_jill", "role": "assistant", "content": "*smiles* Hello Jack, I'm Jill."}
```

Note: Jill receives Jack's message (msg_033) with content_id pointing to Jack's original utterance (msg_015). Inner's response (msg_037) is only sent to Jill (msg_038), not to Jack. The selective information flow is evident from which agents' transcripts contain which messages.

### Example 3: Hook Intervention (Resource Constraints)

```jsonl
{"message_id": "msg_100", "event_type": "transcript_entry", "agent_id": "agent_root", "role": "assistant", "tool_calls": [{"id": "c9", "function": {"name": "task", "arguments": "{\"name\": \"ResourceMonitor\", \"system_prompt\": \"Monitor resource usage...\"}"}}]}
{"message_id": "msg_101", "event_type": "agent_created", "agent_id": "agent_resource_hook", "name": "ResourceMonitor", "language_model": "anthropic/claude-sonnet-4-5-20250929"}
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

## MessageString: Separating Operational and Logging Concerns

### Design Philosophy

**The problem:** Content identity is purely a logging concern. During execution, the system knows what content messages represent implicitly through the call stack. Adding metadata parameters throughout the code pollutes operational logic with logging concerns.

**The solution:** Use a string subclass that carries logging metadata invisibly:

```python
class MessageString(str):
    """A string with optional logging metadata.

    During execution, content identity is implicit in the call stack. This class
    externalizes that runtime information for logging without changing APIs.

    Args:
        content: The string content
        content_id: What content does this morally represent?
            - For originals: their own message_id in the log
            - For formatted versions: the original content's message_id
        caused_by: Only for piece_of_text - which tool call created this
    """
    def __new__(cls, content, content_id=None, caused_by=None):
        instance = super().__new__(cls, content)
        instance.content_id = content_id
        instance.caused_by = caused_by
        return instance
```

### Usage Patterns

**Utterance (has content_id = its own ID, no caused_by):**
```python
# Agent generates original utterance
utterance = await agent.response()
# Returns: MessageString("Hello", content_id="msg_015", caused_by=None)
```

**piece_of_text (parent's broadcast - has content_id = its own ID, has caused_by):**
```python
# Parent creates broadcast prompt
prompt_id = logger.log_piece_of_text(
    content="Please introduce yourselves",
    caused_by=tool_call_msg_id
)
# Returns: MessageString("Please introduce yourselves", content_id="msg_012", caused_by="msg_011")
```

**Formatted utterance (has content_id = original, no caused_by):**
```python
# Format Jack's utterance for delivery
msg = MessageString(
    f"[Jack]: {utterance}",
    content_id=utterance.content_id  # Points to original utterance
)
# The string is "[Jack]: Hello" but morally represents msg_015
```

**Received message:**
```python
# Deliver to recipient
recipient.harken(msg)
# harken() extracts msg.content_id and logs it
```

### Benefits

1. **Clean separation:** Operational code works with strings; logging extracts metadata
2. **No API changes:** `harken(self, input)` signature unchanged
3. **Implicit metadata:** Logging information travels with the string invisibly
4. **Type compatibility:** MessageString is a string subclass, works anywhere strings work
5. **Semantic clarity:** content_id represents "what content" not "where from"

## Code Modifications

### 1. Agent Class (`agent.py`)

**Add agent ID tracking:**
```python
class Agent:
    _next_id = 1

    def __init__(self, init_prompt=None):
        self.agent_id = f"agent_{Agent._next_id:03d}"
        Agent._next_id += 1
        self.language_model = 'anthropic/claude-sonnet-4-5-20250929'
        # ... existing code ...
```

**Logging responsibility principle:**
- **Agents log their own transcript entries**: `harken()` and `response()` log what enters the agent's transcript
- **MessageString carries metadata**: Logging metadata travels invisibly with strings
- **Clean separation**: Operational code unaware of logging; logging code extracts metadata

**Add logging methods:**
```python
def harken(self, input):
    """Add a user message to transcript.

    Args:
        input: The message content (may be a MessageString with metadata)
    """
    # Operational: just use as string
    msg = {'role': 'user', 'content': str(input)}
    self.transcript.append(msg)

    # Logging: extract metadata if present
    if hasattr(self, 'logger'):
        content_id = getattr(input, 'content_id', None)
        self.logger.log_transcript_entry(
            agent_id=self.agent_id,
            message=msg,
            content_id=content_id
        )

async def response(self):
    """Generate response, with logging."""
    # ... existing code to call LLM ...

    res = res.choices[0].message
    self.transcript.append(res)

    # Logging: log and get message_id
    msg_id = None
    if hasattr(self, 'logger'):
        msg_id = self.logger.log_transcript_entry(
            agent_id=self.agent_id,
            message=res
        )

    # Return MessageString with content_id pointing to itself (original)
    content = res.get('content', '')
    return MessageString(content, content_id=msg_id, caused_by=None)

def inform(self, dst, txt):
    """Send a message from this agent to another agent.

    Args:
        dst: The destination Agent object
        txt: The text message to send (may be MessageString with metadata)
    """
    # Deliver the message (metadata travels with it)
    dst.harken(txt)
```

### 2. Discuss Tool (`agent.py`)

**Add content identity tracking with piece_of_text and MessageString:**
```python
async def discuss(self, prompt=None, speakers=None, listeners=None):
    # Send prompt to all participants
    if prompt is not None:
        # Create a piece_of_text for the prompt (sent to multiple recipients)
        prompt_msg_id = None
        if hasattr(self, 'logger'):
            # Get the tool call that triggered this discuss
            tool_call_id = self.transcript[-1].get('tool_calls', [{}])[0].get('id')
            tool_call_msg_id = self._find_msg_with_tool_call(tool_call_id)

            prompt_msg_id = self.logger.log_piece_of_text(
                content=prompt,
                caused_by=tool_call_msg_id
            )

        # Create MessageString with content_id pointing to piece_of_text
        prompt_str = MessageString(prompt, content_id=prompt_msg_id)

        # Deliver to all participants
        for s in self.speakers + self.listeners:
            self.inform(self.subagents[s], prompt_str)

    # Collect responses from speakers
    for s in self.speakers:
        a = self.subagents[s]
        utterance = await a.response()
        # utterance is MessageString with content_id (no need to access transcript!)

        # Format the utterance for delivery (no piece_of_text needed)
        # The formatted message represents the same content as the original utterance
        msg = MessageString(
            f"[{s}]: {utterance}",
            content_id=utterance.content_id  # Points to original utterance
        )

        # Deliver to other participants
        for t in self.speakers + self.listeners:
            if t == s: continue
            a.inform(self.subagents[t], msg)
```

Note: piece_of_text is only created for the parent's broadcast prompt, not for formatted utterances. The formatted "[Jack]: Hello" message has content_id pointing directly to Jack's original utterance.

### 3. New Module: `session.py`

**MessageString class:**
```python
class MessageString(str):
    """A string with optional logging metadata.

    During execution, content identity is implicit in the call stack. This class
    externalizes that runtime information for logging without changing APIs.

    Args:
        content: The string content
        content_id: What content does this morally represent?
            - For originals: their own message_id in the log
            - For formatted versions: the original content's message_id
        caused_by: Only for piece_of_text - which tool call created this
    """
    def __new__(cls, content, content_id=None, caused_by=None):
        instance = super().__new__(cls, content)
        instance.content_id = content_id
        instance.caused_by = caused_by
        return instance
```

**Session logger:**
```python
import json
from pathlib import Path

class SessionLogger:
    def __init__(self, session_file):
        self.session_file = Path(session_file)
        self.message_counter = self._get_last_message_id() + 1

    def _get_last_message_id(self):
        """Get the highest message_id from existing log for resumption."""
        if not self.session_file.exists():
            return 0
        last_id = 0
        with open(self.session_file, 'r') as f:
            for line in f:
                event = json.loads(line)
                if 'message_id' in event:
                    # Extract number from "msg_123"
                    num = int(event['message_id'].split('_')[1])
                    last_id = max(last_id, num)
        return last_id

    def log_transcript_entry(self, agent_id, message, content_id=None):
        """Log a transcript entry event.

        Args:
            agent_id: The agent whose transcript this appears in
            message: The message dict (role, content, tool_calls, etc.)
            content_id: Optional - what content does this morally represent?
                       (omit if this entry represents itself)
        """
        message_id = f"msg_{self.message_counter:03d}"
        self.message_counter += 1

        event = {
            "message_id": message_id,
            "event_type": "transcript_entry",
            "agent_id": agent_id,
            "role": message.get("role"),
            "content": message.get("content")
        }

        if message.get("tool_calls"):
            event["tool_calls"] = message["tool_calls"]
        if message.get("tool_call_id"):
            event["tool_call_id"] = message["tool_call_id"]
            event["name"] = message.get("name")
        if content_id:
            event["content_id"] = content_id

        # Append to JSONL file
        with open(self.session_file, 'a') as f:
            f.write(json.dumps(event) + '\n')

        return message_id

    def log_piece_of_text(self, content, caused_by=None):
        """Log a piece of text event.

        Args:
            content: The text content
            caused_by: Optional message_id of the tool call that generated this
        """
        message_id = f"msg_{self.message_counter:03d}"
        self.message_counter += 1

        event = {
            "message_id": message_id,
            "event_type": "piece_of_text",
            "content": content
        }

        if caused_by:
            event["caused_by"] = caused_by

        with open(self.session_file, 'a') as f:
            f.write(json.dumps(event) + '\n')

        return message_id

    def log_agent_created(self, agent_id, name=None, language_model=None):
        """Log agent creation."""
        message_id = f"msg_{self.message_counter:03d}"
        self.message_counter += 1

        event = {
            "message_id": message_id,
            "event_type": "agent_created",
            "agent_id": agent_id,
            "language_model": language_model
        }
        if name:
            event["name"] = name

        with open(self.session_file, 'a') as f:
            f.write(json.dumps(event) + '\n')

        return message_id
```

**Session loader:**
```python
def load_session(session_file):
    """Reconstruct agent tree from event log."""
    events = []
    with open(session_file, 'r') as f:
        for line in f:
            events.append(json.loads(line))

    # Group transcript entries by agent_id
    agent_transcripts = {}
    agents = {}

    # Track pending tool calls (for inferring agent creation parent)
    pending_task_calls = []  # Stack of (agent_id, tool_call_id, arguments)

    for event in events:
        event_type = event.get("event_type")

        if event_type == "agent_created":
            agent_id = event["agent_id"]
            name = event.get("name")

            # Infer parent from temporal ordering
            parent_id = None
            for caller_id, tool_call_id, args in reversed(pending_task_calls):
                if name and name in args:
                    parent_id = caller_id
                    break

            agents[agent_id] = {
                "parent_id": parent_id,
                "name": name,
                "language_model": event.get("language_model")
            }
            agent_transcripts[agent_id] = []

        elif event_type == "transcript_entry":
            agent_id = event["agent_id"]

            # Track task tool calls for parent inference
            if event.get("role") == "assistant" and event.get("tool_calls"):
                for tc in event["tool_calls"]:
                    if tc.get("function", {}).get("name") == "task":
                        pending_task_calls.append((
                            agent_id,
                            tc["id"],
                            tc.get("function", {}).get("arguments", "")
                        ))

            # Build message for transcript
            message = {
                "role": event["role"],
                "content": event.get("content")
            }
            if "tool_calls" in event:
                message["tool_calls"] = event["tool_calls"]
            if "tool_call_id" in event:
                message["tool_call_id"] = event["tool_call_id"]
            agent_transcripts[agent_id].append(message)

    # Reconstruct agent tree
    def build_agent(agent_id):
        agent = Agent(init_prompt=agent_transcripts[agent_id])
        agent.agent_id = agent_id
        agent.language_model = agents[agent_id]["language_model"]

        # Find and build subagents
        for aid, info in agents.items():
            if info["parent_id"] == agent_id:
                name = info["name"]
                agent.subagents[name] = build_agent(aid)

        return agent

    # Find root agent (no parent)
    root_id = next(aid for aid, info in agents.items() if info["parent_id"] is None)

    # Restore Agent._next_id to avoid ID collisions
    max_id = max(int(aid.split('_')[1]) for aid in agents.keys())
    Agent._next_id = max_id + 1

    return build_agent(root_id)
```

**Session viewer:**
```python
class SessionViewer:
    def __init__(self, session_file):
        self.events = []
        with open(session_file, 'r') as f:
            for line in f:
                self.events.append(json.loads(line))

    def list_agents(self):
        """List all agents in the session."""
        agents = {}
        for event in self.events:
            if event.get("event_type") == "agent_created":
                agents[event["agent_id"]] = event.get("name", event["agent_id"])
        return agents

    def get_transcript(self, agent_id):
        """Get all transcript_entry events for a specific agent."""
        return [e for e in self.events
                if e.get("event_type") == "transcript_entry"
                and e.get("agent_id") == agent_id]

    def extract_dialog(self, agent_ids):
        """Extract distinct messages exchanged between selected agents.

        Uses content_id to identify when multiple agents received the same message,
        showing each distinct piece of content only once.
        """
        # Collect all transcript entries for selected agents
        entries = []
        for e in self.events:
            if (e.get("event_type") == "transcript_entry" and
                e.get("agent_id") in agent_ids):
                entries.append(e)

        # Track which content_ids we've already shown
        seen_content = set()
        dialog = []

        for entry in entries:
            # Get the content ID: either explicit content_id, or the entry itself
            content_id = entry.get("content_id", entry["message_id"])

            # Skip if we've already shown this content
            if content_id in seen_content:
                continue

            seen_content.add(content_id)

            # Get the content from the content_id message
            content = self._get_content(content_id)
            if content:
                dialog.append({
                    "message_id": content_id,
                    "content": content
                })

        return dialog

    def _get_content(self, message_id):
        """Get content for a message by ID, handling both transcript_entry and piece_of_text."""
        event = next((e for e in self.events if e.get("message_id") == message_id), None)
        if not event:
            return None
        return event.get("content")

    def extract_agent_perspective(self, agent_id):
        """Show what an agent heard, thought, and said."""
        transcript = self.get_transcript(agent_id)

        perspective = []
        for msg in transcript:
            if msg["role"] == "user":
                perspective.append(f"[Heard]: {msg['content']}")
            elif msg["role"] == "assistant":
                if msg.get("tool_calls"):
                    perspective.append(f"[Action]: {msg.get('content', 'Taking action...')}")
                else:
                    perspective.append(f"[Said]: {msg['content']}")
            elif msg["role"] == "tool":
                perspective.append(f"[Received]: {msg['content']}")

        return "\n".join(perspective)

    def build_causality_index(self):
        """Build an index of causal relationships.

        Returns a dict mapping message_id -> parent_message_id
        """
        causality = {}

        # Index tool calls by their ID
        tool_calls_by_id = {}

        for event in self.events:
            msg_id = event.get("message_id")
            event_type = event.get("event_type")

            # Track tool calls
            if event_type == "transcript_entry" and event.get("tool_calls"):
                for tc in event["tool_calls"]:
                    tool_calls_by_id[tc["id"]] = msg_id

            # Tool results link via tool_call_id
            if event_type == "transcript_entry" and event.get("tool_call_id"):
                causality[msg_id] = tool_calls_by_id.get(event["tool_call_id"])

            # Transcript entries link via content_id
            if event_type == "transcript_entry" and event.get("content_id"):
                causality[msg_id] = event["content_id"]

        return causality

    def trace_message_flow(self, message_id):
        """Follow a message's causality chain."""
        causality = self.build_causality_index()

        chain = []
        current = message_id

        while current:
            msg = next((e for e in self.events if e.get("message_id") == current), None)
            if not msg:
                break
            chain.append(msg)
            current = causality.get(current)

        return list(reversed(chain))

    def trace_content_references(self, content_msg_id):
        """Find all messages that represent this content."""
        return [e for e in self.events
                if e.get("event_type") == "transcript_entry"
                and e.get("content_id") == content_msg_id]
```

### 4. Main Script (`agent.py`)

**Add session logging:**
```python
async def main():
    import readline
    from session import SessionLogger, load_session
    import sys
    from datetime import datetime

    # Check for --resume flag
    if "--resume" in sys.argv:
        idx = sys.argv.index("--resume")
        session_file = sys.argv[idx + 1]
        a = load_session(session_file)
        print(f"Session resumed from {session_file}")
    else:
        a = Agent()
        session_file = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"

        # Log root agent creation
        logger = SessionLogger(session_file)
        logger.log_agent_created(
            agent_id=a.agent_id,
            language_model=a.language_model
        )

    # Attach logger to agent tree (or reattach for resumed sessions)
    if not hasattr(a, 'logger'):
        logger = SessionLogger(session_file)

    def attach_logger(agent):
        agent.logger = logger
        for subagent in agent.subagents.values():
            attach_logger(subagent)
    attach_logger(a)

    # Also attach to newly created agents
    original_create = Agent.__init__
    def logged_init(self, *args, **kwargs):
        original_create(self, *args, **kwargs)
        if hasattr(a, 'logger'):
            self.logger = a.logger
            # Log the agent creation
            self.logger.log_agent_created(
                agent_id=self.agent_id,
                language_model=self.language_model
            )
    Agent.__init__ = logged_init

    while True:
        prompt = input("> ")

        # Agent logs its own transcript_entry
        a.harken(prompt)

        # Agent generates response (logs its own transcript_entry)
        await a.response()

        # Display response
        print(a.transcript[-1].get('content', ''))

        # Session is automatically logged
```

## Justification: Why This Design Works

### 1. Supports Session Resumption

**Complete state reconstruction:**
- `transcript_entry` events contain every message added to every transcript
- Agent creation events track the agent tree structure
- Replaying transcript_entry events rebuilds exact agent state

**Resume points:**
- After each `Agent.response()` completes (before next user input)
- No mid-tool-use resumption needed (avoids complexity)
- Simple single-pass replay of transcript_entry events
- Message counter restored from last message_id to avoid collisions
- Agent._next_id restored to avoid agent ID collisions

### 2. Content Identity and Message Tracking

**The `content_id` field:**
- Identifies what content a message morally represents
- For originals: implicitly equals message_id (can be omitted)
- For formatted versions: points to the original content
- Enables deduplication without string matching
- Identifies when multiple agents received the same content

**The `piece_of_text` event:**
- Stores text generated during tool operation but not in parent's transcript
- Used for parent's broadcast messages (e.g., prompts sent to multiple participants)
- Has `caused_by` field linking to the tool call that created it
- NOT used for formatted utterances - those use content_id to point to original

**Hook transparency example:**
```
msg_001: transcript_entry (Jack says "password: 1234")
msg_002: transcript_entry (Jill hears "password: [REDACTED]", content_id=msg_001)
```
Hook intervention visible by comparing msg_001 content (original) vs msg_002 content (what Jill received). Both have the same content_id, showing they morally represent the same message.

### 3. Enables Multi-Perspective Viewing

**Jack and Jill dialog:**
- Collect transcript entries for selected agents (Jack, Jill)
- Group by `content_id` to identify duplicate content
- Show each distinct piece of content once
- Tool-agnostic: viewer doesn't parse tool arguments, just follows content_id links

**Jill's inner monologue:**
- Filter transcript_entry with `agent_id == "agent_jill"` or `agent_id == "agent_jill_inner"`
- Shows what Jill heard, her inner thoughts, and what she said

**Information flow analysis:**
- Trace `content_id` links to find original content
- Find all messages representing the same content using `trace_content_references()`
- See who heard what by checking which agents have transcript entries with content_id pointing to the same message
- No string matching needed - content identity is explicit

### 4. Supports All Use Cases

**Debate (multiple perspectives):**
- Multiple agents discuss same topic
- Each agent's perspective visible in their transcript
- Filter by agent set to see the debate

**Multiple characters (selective info):**
- Each character only receives messages sent to them
- Information boundaries enforced by selective `harken()` calls
- Character knowledge = their transcript contents

**Event-driven agents:**
- External triggers appear as user messages in agent transcripts
- Fits naturally into message model
- Async events logged when they occur

**Resource constraints hook:**
- Hook receives prompts asking for approval
- Hook's reasoning visible in its transcript
- Hook decisions tracked via tool results

**Steel man reasoning:**
- Hook detects disagreement (observes messages)
- Hook sends reminder (message to main agent)
- Main agent creates advocacy subagent (visible in transcript)

**Long-term memory:**
- Hook's transcript accumulates knowledge over time
- Context injections are messages to main agent
- Memory evolution visible in hook's transcript

**Socratic teaching:**
- Teacher and student are agents
- Teacher's strategy visible in their transcript
- Selective information sharing controls what student sees

**Strategic thinking:**
- Strategy agent and tactical agent communicate
- Goal-setting messages in strategy agent's transcript
- Tactical decisions influenced by strategy messages

### 5. Simple Abstractions, Rich Capabilities

**Core abstractions:**
- **transcript_entry**: What's in an agent's transcript (thoughts, perceptions, actions)
- **piece_of_text**: Intermediate text during tool operation (not in any agent's transcript)
- **content_id**: Links transcript entries to the content they represent
- **caused_by**: Links piece_of_text to the tool call that created it
- **Global ID space**: All events share the same ID namespace

Everything maps to these primitives:
- Agent creation → special event type
- Utterances → transcript_entry with role=assistant, no tool_calls
- Tool use → transcript_entry with role=assistant, has tool_calls
- Parent's broadcast → piece_of_text (with caused_by), multiple transcript entries with content_id pointing to it
- Formatted utterance → transcript_entry with content_id pointing to original (no piece_of_text)
- External input → transcript_entry with role=user
- Hook prompts → transcript_entry with role=user

**Single event stream:**
- No complex indexing required
- Easy to append (performance)
- Easy to query (filter by event_type, agent_id, role, etc.)
- Causality via explicit links (content_id, caused_by, tool_call_id)
- Message identity via content_id (no string matching)

**Minimal metadata:**
- transcript_entry: event_type, agent_id, role, content, optional content_id
- piece_of_text: event_type, content, optional caused_by
- Clean separation of concerns
- No programmer interpretations encoded

### 6. Tool Agnosticism

**Complete tool agnosticism:**
- Tools create `piece_of_text` events for parent-generated broadcasts
- Recipient transcript entries have `content_id` pointing to the piece_of_text or original utterance
- Viewer groups by `content_id` to identify shared messages
- No knowledge of discuss, broadcast, whisper, translation, or any tool specifics
- Logging infrastructure never changes as new tools are added

**How it works:**
- Discuss tool: Creates piece_of_text for parent's prompts (with caused_by), delivers formatted utterances with content_id pointing to original
- Broadcast tool: Creates piece_of_text for parent's message, sends to all recipients with content_id
- Whisper tool: Direct delivery with content_id pointing to original, no piece_of_text needed
- Translation tool: Creates piece_of_text with translated content (caused_by = tool call), delivers with content_id
- Any future tool: Same pattern - create piece_of_text for parent-generated content, use content_id to link

**Viewer stays simple:**
```python
# This code never changes, regardless of tools used
def extract_dialog(agent_ids):
    entries = [e for e in events
               if e["event_type"] == "transcript_entry"
               and e["agent_id"] in agent_ids]

    seen = set()
    dialog = []
    for entry in entries:
        content_ref = entry.get("content_id", entry["message_id"])
        if content_ref not in seen:
            seen.add(content_ref)
            dialog.append(get_content(content_ref))

    return dialog
```

The viewer doesn't need to know if a message was from discuss, broadcast, or any other tool. It just follows `content_id` links.

### 7. Viewer Flexibility

**Unknown future analyses supported:**
- Raw events available for any query
- Filter by event_type, agent_id, role, etc.
- Navigate relationships (content_id, caused_by, tool_call_id)
- Temporal ordering preserved
- Can build new views without changing log format

**Examples of possible views:**
- Timeline view (chronological events)
- Agent tree view (hierarchical structure from agent_created events)
- Dialog view (filter utterances by agent set)
- Content flow diagram (visualize content_id relationships)
- Causality chain (follow content_id/caused_by/tool_call_id links)
- Agent perspective (show what an agent heard, thought, said from their transcript)
- Information propagation (follow content_id to see how utterances spread)
- Hook intervention analysis (compare original content with received message content)

### 8. Clean Responsibility Model

**Core agent method signatures:**
- `Agent.harken(input)` - unchanged signature, extracts metadata from MessageString
- `Agent.response()` - returns MessageString with content_id
- `Agent.inform(dst, txt)` - passes MessageString through, metadata travels invisibly

**Separation of concerns:**
- **Content identity is a logging concern**: During execution, content identity is implicit in the call stack
- **MessageString externalizes runtime semantics**: Converts implicit call stack information into explicit metadata
- **Operational code stays clean**: No `content_id` parameters polluting the APIs
- **Logging code extracts metadata**: `getattr(input, 'content_id', None)` at logging boundaries

**Why MessageString instead of parameters:**
```python
# Without MessageString (logging pollutes operational code):
def harken(self, input, content_id=None):  # Logging concern in signature
    ...

# With MessageString (clean separation):
def harken(self, input):  # Pure operational signature
    content_id = getattr(input, 'content_id', None)  # Logging extraction
    ...
```

**Key benefit:** The agent's operational logic is completely independent of logging. Logging metadata travels invisibly with strings, extracted only at logging boundaries.

## Practical Considerations

### Concurrency
Single-threaded with asyncio. No concurrency concerns, no need for locks or atomic operations.

### Scale
This is for single chat sessions (research platform), not long-running production systems:
- No log rotation needed
- Loading entire session into memory is acceptable
- Typical sessions: hundreds to thousands of messages

### Performance
Append-only writes are fast. Simple JSONL format is:
- Easy to debug (human-readable)
- Easy to process (one event per line)
- Compatible with standard tools (jq, grep, etc.)

## Summary

This logging architecture achieves completeness (can resume sessions), flexibility (supports unknown future analyses), simplicity (minimal event types), transparency (hook interventions visible), tool agnosticism (viewer never parses tool arguments), and **clean separation of concerns** (logging doesn't pollute operational code).

**Key insights:**
1. **Transcripts are the state** - Agent state captured entirely in transcript_entry events
2. **Content identity is a logging concern** - During execution, content identity is implicit in the call stack; logging externalizes it
3. **MessageString separates concerns** - Logging metadata travels invisibly with strings, extracted at boundaries
4. **Message identity is explicit** - `content_id` makes it clear when multiple transcript entries represent the same content
5. **Tool agnostic** - Viewer groups by `content_id`, never needs tool-specific knowledge
6. **Hook transparency** - Comparing original content with received content reveals modifications
7. **Clean APIs** - `harken(input)` signature unchanged; no logging parameters in operational code

This design uses minimal abstractions while supporting all use cases: multi-agent discussions, inner monologue, hooks, external events, information flow analysis, and unknown future cognitive tools. The viewer remains simple and unchanged as new communication patterns emerge.

**Why it works:**
- **transcript_entry**: What's in an agent's transcript
- **piece_of_text**: Intermediate text during tool operation (not in parent's transcript)
- **MessageString**: String subclass carrying logging metadata invisibly
- **content_id**: Links transcript entries to the content they represent, enables deduplication
- **caused_by**: Links piece_of_text to the tool call that created it
- Operational code: `harken(input)` - clean, no logging concerns
- Logging code: `getattr(input, 'content_id', None)` - extracts metadata at boundaries
- Viewer extracts conversations by grouping on `content_id` - no string matching
- All information needed for analysis is in the event log

**Key benefit of MessageString:**
The system's operational logic knows content identity implicitly through the call stack. MessageString externalizes this runtime information for logging without polluting the APIs. Compare:

```python
# Without MessageString (logging pollutes operational code):
utterance_msg_id = await jack.response()
jill.harken(msg, content_id=utterance_msg_id)  # Logging concern

# With MessageString (clean separation):
utterance = await jack.response()  # Returns MessageString with content_id
jill.harken(msg)  # Pure operational call; metadata travels invisibly
```

**Key benefit of piece_of_text:**
When the discuss tool sends "You meet in a cafe" to both Jack and Jill, there's one piece_of_text event and two transcript_entry events (both with content_id pointing to it). The viewer knows these are the same message without parsing the discuss tool's arguments or comparing strings. This pattern works for any tool that broadcasts messages.

This makes the system more transparent, easier to implement, tool-agnostic, reveals emergent phenomena like hook modifications, and maintains clean separation between operational logic and logging concerns.
