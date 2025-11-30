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
- **Parent relationship**: Inferred from causality chain (agent creation caused by parent's tool call)
- **Metadata**: `language_model`, creation context

### 2. Messages (Transcript Entries)

Messages are the fundamental unit of logging. Each message represents an entry in an agent's transcript:
- User inputs (from user, other agents, or system)
- Agent responses (utterances or tool calls)
- Tool results
- External triggers (events from outside world)
- System notifications (hook events, orchestration)

Each message has:
- **Identity**: `message_id` (unique), `agent_id` (whose transcript)
- **Content**: `role`, `content`, `tool_calls`, etc.
- **Utterance reference**: `utterance_ref` (optional) - points to another message when this message represents the same semantic utterance
- **Causality**: `caused_by` - what prompted this message
- **Source**: `source` - where this message came from (agent_id, "external", or "system")

### 3. Utterances

An **utterance** is an assistant message without tool calls - it represents an agent communicating rather than taking actions. Utterances are shared with other agents (or the user).

**Identifying utterances**: Look for assistant role messages that have `content` but no `tool_calls`.

When an utterance is delivered to other agents, those delivery messages include `utterance_ref` pointing to the original utterance message. This enables:
- Tracking message lineage (original → prefixed → transformed)
- Identifying who said what without tool-specific patterns
- Tool-agnostic viewer (just filter by original utterances)

**Example**: Jack says "Hello" in a discussion:
1. Jack's assistant message (the original utterance): `msg_012`
2. Discussion chair receives it as tool result: `msg_013` with `utterance_ref: "msg_012"`
3. Jill receives it as user message: `msg_014` with `utterance_ref: "msg_012"` and content "[Jack]: Hello"

**Note**: Assistant messages that contain both `content` and `tool_calls` are NOT utterances. The content in such messages is internal thinking/explanation (e.g., "Let me think about that...") and is not shared with other agents.

### 4. Message Sources

Messages can come from:
- **Another agent** (`source: agent_id`)
- **External world** (`source: "external"`) - user input, file changes, async events
- **System orchestrator** (`source: "system"`) - hook notifications, system events

This forms a **Lamport clock**: message causality relationships establish causal-temporal ordering without requiring explicit timestamps.

## Log Format

### Event Stream Structure

Append-only JSONL file where each line is an event (agent creation or message):

```jsonl
{"message_id": "msg_001", "event_type": "agent_created", "agent_id": "agent_001", "language_model": "anthropic/claude-sonnet-4-5-20250929"}
{"message_id": "msg_002", "agent_id": "agent_001", "role": "user", "content": "Create Jack and Jill", "source": "external"}
{"message_id": "msg_003", "agent_id": "agent_001", "role": "assistant", "content": "I'll create two agents...", "tool_calls": [...], "caused_by": "msg_002"}
{"message_id": "msg_004", "event_type": "agent_created", "agent_id": "agent_002", "caused_by": "msg_003", "name": "Jack", "language_model": "anthropic/claude-sonnet-4-5-20250929"}
{"message_id": "msg_005", "agent_id": "agent_002", "role": "assistant", "content": "Hi", "caused_by": "msg_004"}
{"message_id": "msg_006", "agent_id": "agent_003", "role": "user", "content": "[Jack]: Hi", "source": "agent_002", "utterance_ref": "msg_005", "caused_by": "msg_005"}
```

### Message Event Schema

**Core fields** (always present):
```json
{
  "message_id": "msg_123",      // Unique identifier
  "agent_id": "agent_001",      // Whose transcript this appears in
  "role": "user|assistant|tool|system",
  "content": "..."              // Message content
}
```

**Flow metadata** (when applicable):
```json
{
  "source": "agent_002|external|system",  // Where this message came from
  "caused_by": "msg_122",                 // What prompted this message
  "utterance_ref": "msg_120"              // If this represents the same utterance as another message
}
```

**Tool calls** (for assistant messages):
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

**Tool results** (for tool role messages):
```json
{
  "tool_call_id": "call_abc",
  "name": "task",
  "content": "Created subagent: Jack"
}
```

### Special Event: Agent Creation

```json
{
  "message_id": "msg_004",
  "event_type": "agent_created",
  "agent_id": "agent_002",
  "caused_by": "msg_003",
  "name": "Jack",
  "language_model": "anthropic/claude-sonnet-4-5-20250929"
}
```

The parent agent is inferred by following `caused_by` to the tool call that created this agent. That tool call's `agent_id` is the parent.

## Concrete Examples

### Example 1: Jack and Jill Discussion

```jsonl
{"message_id": "msg_001", "event_type": "agent_created", "agent_id": "agent_root"}
{"message_id": "msg_002", "agent_id": "agent_root", "role": "user", "content": "Create Jack and Jill for a cafe discussion", "source": "external"}
{"message_id": "msg_003", "agent_id": "agent_root", "role": "assistant", "tool_calls": [{"id": "c1", "function": {"name": "task", "arguments": "{\"name\": \"Jack\", \"system_prompt\": \"You work in HR...\"}"}}], "caused_by": "msg_002"}
{"message_id": "msg_004", "event_type": "agent_created", "agent_id": "agent_jack", "caused_by": "msg_003", "name": "Jack"}
{"message_id": "msg_005", "agent_id": "agent_jack", "role": "system", "content": "You work in HR..."}
{"message_id": "msg_006", "agent_id": "agent_root", "role": "tool", "tool_call_id": "c1", "content": "Created subagent: Jack", "caused_by": "msg_003"}
{"message_id": "msg_007", "agent_id": "agent_root", "role": "assistant", "tool_calls": [{"id": "c2", "function": {"name": "task", "arguments": "{\"name\": \"Jill\", \"system_prompt\": \"You are an aspiring author...\"}"}}], "caused_by": "msg_006"}
{"message_id": "msg_008", "event_type": "agent_created", "agent_id": "agent_jill", "caused_by": "msg_007", "name": "Jill"}
{"message_id": "msg_009", "agent_id": "agent_jill", "role": "system", "content": "You are an aspiring author..."}
{"message_id": "msg_010", "agent_id": "agent_root", "role": "tool", "tool_call_id": "c2", "content": "Created subagent: Jill", "caused_by": "msg_007"}
{"message_id": "msg_011", "agent_id": "agent_root", "role": "assistant", "tool_calls": [{"id": "c3", "function": {"name": "discuss", "arguments": "{\"prompt\": \"You meet in a cafe. Introduce yourselves.\", \"speakers\": [\"Jack\", \"Jill\"]}"}}], "caused_by": "msg_010"}
{"message_id": "msg_012", "agent_id": "agent_jack", "role": "user", "content": "You meet in a cafe. Introduce yourselves.", "source": "agent_root", "caused_by": "msg_011"}
{"message_id": "msg_013", "agent_id": "agent_jill", "role": "user", "content": "You meet in a cafe. Introduce yourselves.", "source": "agent_root", "caused_by": "msg_011"}
{"message_id": "msg_014", "agent_id": "agent_jack", "role": "assistant", "content": "Hi, I'm Jack. *extends hand*", "caused_by": "msg_012"}
{"message_id": "msg_015", "agent_id": "agent_root", "role": "tool", "tool_call_id": "c3", "content": "Hi, I'm Jack. *extends hand*", "utterance_ref": "msg_014", "caused_by": "msg_014"}
{"message_id": "msg_016", "agent_id": "agent_jill", "role": "user", "content": "[Jack]: Hi, I'm Jack. *extends hand*", "source": "agent_jack", "utterance_ref": "msg_014", "caused_by": "msg_014"}
{"message_id": "msg_017", "agent_id": "agent_jill", "role": "assistant", "content": "*smiles* Hello Jack, I'm Jill.", "caused_by": "msg_016"}
{"message_id": "msg_018", "agent_id": "agent_root", "role": "tool", "tool_call_id": "c3", "content": "*smiles* Hello Jack, I'm Jill.", "utterance_ref": "msg_017", "caused_by": "msg_017"}
{"message_id": "msg_019", "agent_id": "agent_jack", "role": "user", "content": "[Jill]: *smiles* Hello Jack, I'm Jill.", "source": "agent_jill", "utterance_ref": "msg_017", "caused_by": "msg_017"}
```

### Example 2: Inner Monologue

```jsonl
{"message_id": "msg_020", "agent_id": "agent_jill", "role": "assistant", "tool_calls": [{"id": "c4", "function": {"name": "task", "arguments": "{\"name\": \"Inner\", \"system_prompt\": \"You are Jill's inner voice...\"}"}}]}
{"message_id": "msg_021", "event_type": "agent_created", "agent_id": "agent_jill_inner", "caused_by": "msg_020", "name": "Inner"}
{"message_id": "msg_022", "agent_id": "agent_jill_inner", "role": "system", "content": "You are Jill's inner voice..."}
{"message_id": "msg_023", "agent_id": "agent_jill", "role": "user", "content": "[Jack]: Hi, I'm Jack. *extends hand*", "source": "agent_jack", "utterance_ref": "msg_014"}
{"message_id": "msg_024", "agent_id": "agent_jill", "role": "assistant", "tool_calls": [{"id": "c5", "function": {"name": "discuss", "arguments": "{\"speakers\": [\"Inner\"], \"prompt\": \"Jack just introduced himself. What should I say?\"}"}}], "caused_by": "msg_023"}
{"message_id": "msg_025", "agent_id": "agent_jill_inner", "role": "user", "content": "Jack just introduced himself. What should I say?", "source": "agent_jill", "caused_by": "msg_024"}
{"message_id": "msg_026", "agent_id": "agent_jill_inner", "role": "assistant", "content": "Be friendly but not over-eager. A simple greeting with a smile.", "caused_by": "msg_025"}
{"message_id": "msg_027", "agent_id": "agent_jill", "role": "tool", "tool_call_id": "c5", "content": "Be friendly but not over-eager. A simple greeting with a smile.", "utterance_ref": "msg_026", "caused_by": "msg_026"}
{"message_id": "msg_028", "agent_id": "agent_jill", "role": "assistant", "content": "*smiles* Hello Jack, I'm Jill.", "caused_by": "msg_027"}
```

Note: Inner's response (msg_026) is only delivered to Jill (via tool result msg_027). It's not a public utterance to Jack, so only Jill receives it.

### Example 3: Hook Intervention (Resource Constraints)

```jsonl
{"message_id": "msg_100", "agent_id": "agent_root", "role": "assistant", "tool_calls": [{"id": "c9", "function": {"name": "task", "arguments": "{\"name\": \"ResourceMonitor\", \"system_prompt\": \"Monitor resource usage...\"}"}}]}
{"message_id": "msg_101", "event_type": "agent_created", "agent_id": "agent_resource_hook", "caused_by": "msg_100", "name": "ResourceMonitor"}
{"message_id": "msg_102", "agent_id": "agent_root", "role": "assistant", "tool_calls": [{"id": "c10", "function": {"name": "task", "arguments": "{\"name\": \"Searcher4\"}"}}]}
{"message_id": "msg_103", "agent_id": "agent_resource_hook", "role": "user", "content": "Agent 'agent_root' is attempting to create subagent 'Searcher4'. Current subagent count: 3. Approve?", "source": "system"}
{"message_id": "msg_104", "agent_id": "agent_resource_hook", "role": "assistant", "content": "DENY. Maximum subagents (3) already reached.", "caused_by": "msg_103"}
{"message_id": "msg_105", "agent_id": "agent_root", "role": "tool", "tool_call_id": "c10", "content": "Error: Action blocked by hook 'ResourceMonitor': Maximum subagents (3) already reached.", "caused_by": "msg_102"}
```

### Example 4: External Trigger (Event-Driven)

```jsonl
{"message_id": "msg_200", "agent_id": "agent_watcher", "role": "user", "content": "File changed: data.json", "source": "external"}
{"message_id": "msg_201", "agent_id": "agent_watcher", "role": "assistant", "content": "I'll reload the data and notify the main agent.", "caused_by": "msg_200"}
```

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

**Add logging hooks:**
```python
def inform(self, input, source=None, utterance_ref=None):
    """Add a user message to transcript, with logging."""
    msg = {'role':'user', 'content':input}
    self.transcript.append(msg)

    if hasattr(self, 'logger'):
        msg_id = self.logger.log_message(
            agent_id=self.agent_id,
            message=msg,
            source=source,
            utterance_ref=utterance_ref
        )
        return msg_id

async def response(self, input=None):
    """Generate response, with logging."""
    # ... existing code to add user message and call LLM ...

    res = res.choices[0].message
    self.transcript.append(res)

    if hasattr(self, 'logger'):
        msg_id = self.logger.log_message(
            agent_id=self.agent_id,
            message=res,
            caused_by=self.last_user_message_id  # Track causality
        )

        # Return the message_id if this is an utterance (no tool_calls)
        if res.get('content') and not res.get('tool_calls'):
            return msg_id

    # ... rest of existing code ...
```

### 2. Discuss Tool (`agent.py`)

**Add message flow tracking:**
```python
async def discuss(self, prompt=None, speakers=None, listeners=None):
    # Send prompt
    if prompt is not None:
        for s in self.speakers + self.listeners:
            self.subagents[s].inform(
                prompt,
                source=self.agent_id
            )

    # Collect responses
    for s in self.speakers:
        a = self.subagents[s]
        utterance_msg_id = await a.response()  # Returns msg_id if utterance

        if utterance_msg_id:
            # Get the content from the utterance
            utterance = a.transcript[-1].get('content', '')

            # Deliver to other participants with utterance_ref
            for t in self.speakers + self.listeners:
                if t == s: continue
                msg = f"[{s}]: {utterance}"
                self.subagents[t].inform(
                    msg,
                    source=a.agent_id,
                    utterance_ref=utterance_msg_id
                )
```

### 3. New Module: `session.py`

**Session logger:**
```python
import json
from pathlib import Path

class SessionLogger:
    def __init__(self, session_file):
        self.session_file = Path(session_file)
        self.message_counter = 1

    def log_message(self, agent_id, message, source=None, caused_by=None, utterance_ref=None):
        """Log a message event."""
        message_id = f"msg_{self.message_counter:03d}"
        self.message_counter += 1

        event = {
            "message_id": message_id,
            "agent_id": agent_id,
            "role": message.get("role"),
            "content": message.get("content")
        }

        if source:
            event["source"] = source
        if caused_by:
            event["caused_by"] = caused_by
        if utterance_ref:
            event["utterance_ref"] = utterance_ref
        if message.get("tool_calls"):
            event["tool_calls"] = message["tool_calls"]
        if message.get("tool_call_id"):
            event["tool_call_id"] = message["tool_call_id"]

        # Append to JSONL file
        with open(self.session_file, 'a') as f:
            f.write(json.dumps(event) + '\n')

        return message_id

    def log_agent_created(self, agent_id, caused_by=None, name=None, language_model=None):
        """Log agent creation."""
        message_id = f"msg_{self.message_counter:03d}"
        self.message_counter += 1

        event = {
            "message_id": message_id,
            "event_type": "agent_created",
            "agent_id": agent_id,
            "language_model": language_model
        }
        if caused_by:
            event["caused_by"] = caused_by
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

    # Build event lookup
    event_by_id = {e.get("message_id"): e for e in events if "message_id" in e}

    # Group messages by agent_id
    agent_transcripts = {}
    agents = {}

    for event in events:
        if event.get("event_type") == "agent_created":
            agent_id = event["agent_id"]

            # Infer parent from causality chain
            parent_id = None
            if "caused_by" in event:
                creation_tool_call = event_by_id[event["caused_by"]]
                parent_id = creation_tool_call["agent_id"]

            agents[agent_id] = {
                "parent_id": parent_id,
                "name": event.get("name"),
                "language_model": event.get("language_model")
            }
            agent_transcripts[agent_id] = []
        elif "agent_id" in event:
            # Regular message
            agent_id = event["agent_id"]
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
        """Get all messages for a specific agent."""
        return [e for e in self.events if e.get("agent_id") == agent_id]

    def extract_dialog(self, agent_ids):
        """Extract just the public utterances from specified agents."""
        # Find original utterances (assistant messages without tool_calls)
        utterances = []
        for e in self.events:
            if (e.get("agent_id") in agent_ids and
                e.get("role") == "assistant" and
                e.get("content") and
                not e.get("tool_calls")):
                utterances.append(e)
        return utterances

    def extract_agent_perspective(self, agent_id):
        """Show what an agent heard, thought, and said."""
        transcript = self.get_transcript(agent_id)

        perspective = []
        for msg in transcript:
            if msg.get("event_type") == "agent_created":
                continue
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

    def trace_message_flow(self, message_id):
        """Follow a message's causality chain."""
        chain = []
        current = message_id

        while current:
            msg = next((e for e in self.events if e.get("message_id") == current), None)
            if not msg:
                break
            chain.append(msg)
            current = msg.get("caused_by")

        return list(reversed(chain))

    def trace_utterance_delivery(self, utterance_msg_id):
        """Find all messages that reference a given utterance."""
        return [e for e in self.events if e.get("utterance_ref") == utterance_msg_id]
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

    # Attach logger to agent tree
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
    Agent.__init__ = logged_init

    while True:
        prompt = input("> ")
        response = await a.response(prompt)
        print(response)

        # Session is automatically logged via logging hooks
```

## Justification: Why This Design Works

### 1. Supports Session Resumption

**Complete state reconstruction:**
- Event log contains every message added to every transcript
- Agent creation events track the agent tree structure
- Replaying events rebuilds exact state

**Resume points:**
- MVP: After each `Agent.response()` completes (before next user input)
- No mid-tool-use resumption needed (avoids complexity)
- Simple single-pass replay of events

### 2. Enables Multi-Perspective Viewing

**Jack and Jill dialog:**
- Filter messages where `role == "assistant"`, `agent_id in [Jack, Jill]`, has content, no tool_calls
- Shows all utterances between them, automatically excluding inner thoughts
- Tool-agnostic: viewer doesn't need to know about discuss implementation

**Jill's inner monologue:**
- Filter events with `agent_id == "agent_jill"` or `agent_id == "agent_jill_inner"`
- Shows what Jill heard, her inner thoughts, and what she said

**Message lineage:**
- Follow `caused_by` backward to trace causality
- Follow `utterance_ref` to find original utterance
- Use `trace_utterance_delivery()` to see who received an utterance

**Hook analysis:**
- Filter events with `source == "system"` to see hook notifications
- Filter by hook agent_id to see hook reasoning
- Trace hook decisions' impact on main agent

### 3. Supports All Use Cases

**Debate (multiple perspectives):**
- Multiple agents discuss same topic
- Each agent's perspective visible in their transcript
- Filter by agent set to see the debate

**Multiple characters (selective info):**
- Each character only receives messages sent to them
- Information boundaries enforced by selective `inform()` calls
- Character knowledge = their transcript contents

**Event-driven agents:**
- External triggers are messages with `source: "external"`
- Fits naturally into message model
- Async events logged when they occur

**Resource constraints hook:**
- Hook receives system notifications
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

### 4. Simple Abstractions, Rich Capabilities

**Core abstraction: One simple entity**
- **Messages**: Transcript entries (with optional utterance_ref for semantic linking)

Everything maps to messages:
- Agent creation → special event type
- Utterances → assistant message without tool_calls
- Tool use → assistant message with tool_calls
- External events → user message with source="external"
- Hook notifications → user message with source="system"

**Single event stream:**
- No complex indexing required
- Easy to append (performance)
- Easy to query (filter by agent_id, role, source, etc.)
- Lamport clock via message relationships

**Minimal metadata:**
- Messages: agent_id, role, content
- Optional: source, caused_by, utterance_ref, tool_calls, tool_call_id
- No tool-specific patterns required
- Emergent properties inferred from message patterns

### 5. Tool Agnosticism

**Complete tool agnosticism:**
- Tools create utterances (assistant messages without tool_calls)
- Other agents receive those utterances with utterance_ref pointing back
- Viewer only knows: "show me utterances where agent_id in [agents]"
- No knowledge of discuss, broadcast, whisper, translation, or any tool specifics
- Logging infrastructure never changes as new tools are added

**How it works:**
- Discuss tool: Delivers utterances with utterance_ref
- Translation tool: Could create new message with utterance_ref to original
- Whisper tool: Delivers utterance to single recipient with utterance_ref
- Any future tool: Same pattern - deliver with utterance_ref

**Viewer stays simple:**
```python
# This code never changes, regardless of tools used
dialog = [msg for msg in events
          if msg.get("role") == "assistant"
          and msg["agent_id"] in agent_filter
          and msg.get("content")
          and not msg.get("tool_calls")]
```

### 6. Viewer Flexibility

**Unknown future analyses supported:**
- Raw events available for any query
- Filter by any field (agent_id, role, source)
- Navigate relationships (causality, utterance refs)
- Temporal ordering preserved
- Can build new views without changing log format

**Examples of possible views:**
- Timeline view (chronological events)
- Agent tree view (hierarchical structure)
- Dialog view (filter utterances by agent set)
- Hook activity view (filter by source="system")
- Message flow diagram (visualize utterance_ref across transcripts)
- Causality chain (trace caused_by backward)
- Agent perspective (show what an agent heard, thought, said)
- Utterance propagation (follow utterance_ref to see who received what)

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

This logging architecture achieves completeness (can resume sessions), flexibility (supports unknown future analyses), and simplicity (minimal abstractions).

**Key insights:**
1. **Transcripts are the state** - All agent state is captured in transcript messages
2. **Utterances are just messages** - No separate entity needed; use utterance_ref for semantic linking
3. **Tool agnostic** - Viewer filters by role and agent, never needs to know about tool-specific patterns

This design reduces to one core entity (Messages) while supporting all use cases: multi-agent discussions, inner monologue, hooks, external events, and unknown future cognitive tools. The viewer remains simple and unchanged as new communication patterns emerge.
