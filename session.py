"""
LOGGING TRANSCRIPTS AND COMMUNICATION

Everything that is placed into a LLM transcript will be logged as
{message_id, event_type='transcript_entry', agent, role, content}

Sometimes it's useful to also log a plain fragment of text. E.g. in the Discuss tool
the parent sends the same prompt to its subagents. The prompt doesn't appear in
the parent's transcript, but let's give it a message_id, so that the viewer app
can track all the things that this prompt caused:
{message_id, event_type='fragment', agent, content, cause}

These two objects may also have a substance field or a cause field (but not both).
If substance is set, it's a message_id. If cause is set, it may be either a message_id,
or a list of message_ids.
- substance: means that the item is essentially the same as another piece of text
- cause: means that the item was triggered by some other, but it's not the same

To illustrate, here are some examples.

- Consider when an agent uses the Discuss tool among subagents. It sends the same prompt
  to all of them. It creates a {msg_id=X, event_type=fragment, content=prompt, cause=...}, 
  and sends it to each of them, and each of them creates a transcript_entry with substance=X.

- Likewise when a response from one subagent is sent to the other participants, 
  there will be an original {msg_id=X, event_type=transcript_entry, ...} from the
  subagent who's speaking, and this will result in a transcript_entry with substance=X
  in each of the other participants.

- When a fragment of text is created, it is created as the result of the agent's tool use.
  Let's say the tool use is {message_id=X, event_type='transcript_entry', role=tool, ...}.
  The fragment will have cause=X, to indicate that it was created as a consequence
  of the tool use, but it does not have the same substance.

- The role=user messages in an LLM transcript all come from *somewhere*, perhaps some other
  agent's output, perhaps a fragment of text from a parent agent. These transcript entries
  should all have substance set, and it should point to the input message.

- Define an *utterance* to be any LLM result that's just textual content without any tool call. An
  utterance is returned to the parent agent (or to the ultimate end-user) as
  a text string. Since it is an LLM result it's in the transcript of the agent that produced it,
  so it has a event_type=transcript_entry log, with a message_id.
  The substance field is blank, since it is by its nature a novel string.
  We'll also leave cause=blank, to indicate that the cause is the LLM's entire transcript.

- If the LLM response requests tool calls, there will be a transcript_entry with substance=blank
  (since it's by its nature a novel string) and we'll leave cause=blank (to indicate that
  the cause is the agent's entire transcript). The tool call will have 
  {message_id:X, tool_calls:[{id=Y1,...},...]}. Then we'll call the tools, and each will result
  in a transcript_entry with {tool_call:X, tool_call_id:Y1, content, ...}. Note that
  (tool_call, tool_call_id) constitute a logical cause for this entry.
  - If the tool returned a plain string, it's stored in content.
  - If the tool returned a TrackedString(message_id=Z), that means it's a string which is substantively
    the same as another string that has already been logged, e.g. the output of another agent.
    Store {..., substance:Z} to record this fact.
  - If the tool returned a MultiTrackedString(message_ids=Z), that means it's a string that has been
    composed out of one or more other strings. Store {..., cause:Z} to record this fact.
    
- Consider an utterance {msg_id=X, role=assistant, content="hello"} from a subagent.
  The parent may make some minor formatting changes to the string, e.g. 
  change it from TrackedString(msg_id=X, content="hello") to TrackedString(msg_id=X, content="[Jack]: hello"},
  keeping the msg_id unchanged. This way, when it's sent to another agent, that other
  agent will correctly record a transcript_entry with substance=X.
  The parent might also compile the string into its tool-result transcript entry,
  in which case it will specify that the transcript entry has cause=X.
  (We'll also allow cause to be a list, to allow for a tool-result that compiles multiple messages.)

The substance and cause fields will be used by the viewer, to enable deduplication
and tracing of linkages. Setting substance=X implies that the message in question was 
caused by X -- how else could the message have the same substance as X if X did not precede it? --
and so there should never be any case where both substance and cause are set.

To facilitate logging code, we'll use the TrackedString class, which extends str but also
stores message_id. This way, code can pass around TrackedString objects
and (except for logging code) treat them as normal strings.


LOGGING AGENTS THEMSELVES

Every agent that is created will be given a globally unique agent_id.
There's typically a tool call that causes agent creation,
{message_id=X, event_type='transcript_entry', role=assistant, tool_use={id:Y,...},...}
The agent that is created will be logged as
{event_type='agent_created', agent, parent, name, language_model, cause=X.Y}

TODO: should parent and name be put into agent creation messages explicitly,
or should they be parsed from tool use?

There is no need for agent deletion events. An agent may choose to remove a subagent,
but that subagent can be seen as persisting indefinitely, just no longer linked to
by any other agent.
"""

import os
import json
import collections


class Session:
    """Representation of multi-agent state, backed by an event stream"""

    def __init__(self, filename):
        self.agent_id = {'user': 'user'}  # Agent -> agent_id:str. Logs all agents that have ever been used in this session.
        self.next_message_id = 0
        self.next_agent_id = 1
        self._log_filename = filename
        self.interlocutor = None  # At the moment, this is only used trivially. In future there'll be tools that shift the interlocutor.

    TRANSCRIPT_ENTRY = {'event_type', 'agent', 'role', 'content'} # may also have substance or cause
    TOOL_USE_ENTRY = {'event_type', 'agent', 'role', 'tool_call', 'tool_call_id', 'name'} # may also have substance or cause
    FRAGMENT = {'event_type', 'agent', 'content', 'cause'}
    AGENT_CREATED = {'event_type', 'agent', 'name', 'parent', 'cause', 'language_model'}
    LOG_KEY_ORDER = ['message_id', 'event_type', 'agent', 'role', 'content', 'name', 'substance', 'cause', 'parent', 'language_model', 'tool_call', 'tool_call_id']

    def log_transcript_entry(self, agent, **kwargs):
        log = kwargs | {'event_type': 'transcript_entry', 'agent': self.agent_id[agent]}
        return self._write(log, required=self.TRANSCRIPT_ENTRY)
    
    def log_tool_use(self, agent, **kwargs):
        log = kwargs | {'event_type': 'transcript_entry', 'agent': self.agent_id[agent]}
        return self._write(log, required=self.TOOL_USE_ENTRY)

    def logged_fragment(self, agent, content, **kwargs):
        log = kwargs | {'event_type': 'fragment', 'agent': self.agent_id[agent], 'content': content}
        msg_id = self._write(log, required=self.FRAGMENT)
        return TrackedString(content, message_id=msg_id)

    def log_agent_created(self, agent, name, parent, **kwargs):
        if parent == 'user': self.interlocutor = agent
        agent_id = str(self.next_agent_id)
        self.agent_id[agent] = agent_id
        self.next_agent_id = self.next_agent_id + 1
        log = kwargs | {'event_type': 'agent_created', 'agent': agent_id, 'name': name, 'parent': self.agent_id[parent], 'language_model': agent.language_model}
        return self._write(log, required=self.AGENT_CREATED)

    def _write(self, log, required):
        for k in required: assert k in log, f"Log requires field {k}"
        msg_id = str(self.next_message_id)
        self.next_message_id = self.next_message_id + 1
        log = log | {'message_id': msg_id}
        log = {k:v for k,v in log.items() if v is not None}
        log = {k:log[k] for k in self.LOG_KEY_ORDER if k in log} | {k:v for k,v in log.items() if k not in self.LOG_KEY_ORDER}
        with open(self._log_filename, 'a') as f:
            f.write(json.dumps(log) + '\n\n')           
        return msg_id
    
    AgentSpec = collections.namedtuple('AgentSpec', ['language_model', 'transcript', 'subagents'])

    @staticmethod
    def load(filename, construct_agent):
        session = Session(filename)
        agentspec = {}  # agent_id -> AgentSpec
        interlocutor_id = None
        # Replay the event log
        # Note: this code will crash in various ways if the event log is badly formatted or doesn't meet expectations.
        # I'm happy with this, for a research platform. I don't want this code to smooth over glitches in the log file!
        # I could show a more informative error message, but it's not worth it for a research platform.
        max_message_id = -1
        with open(filename, 'r') as f:
            for line in f:
                line = line.strip()
                if not line: continue
                event = json.loads(line)
                msg_id, event_type = event['message_id'], event['event_type']
                if msg_id.isdigit(): max_message_id = max(max_message_id, int(msg_id))
                if event_type == 'agent_created':
                    # Question. Should we rely on special events like this, or should we be parsing the tools?
                    a = Session.AgentSpec(language_model=event['language_model'], transcript=[], subagents={})
                    agent_id, name, parent_id = event['agent'], event['name'], event['parent']
                    agentspec[agent_id] = a
                    if parent_id == 'user':
                        interlocutor_id = agent_id
                    else:
                        agentspec[parent_id].subagents[name] = agent_id
                elif event_type == 'transcript_entry':
                    msg = {'role': event['role']}
                    KEYS = ['content', 'tool_calls', 'name', 'tool_call_id']
                    for k in KEYS:
                        if k in event:
                            msg[k] = event[k]
                    agent_id = event['agent']
                    agentspec[agent_id].transcript.append(msg)
                elif event_type == 'fragment':
                    pass
                else:
                    raise ValueError(event)
        # Restore the state based on the replayed event log
        agents = {} # agent_id -> Agent
        for agent_id,spec in agentspec.items():
            agent = construct_agent(session=session, language_model=spec.language_model, transcript=spec.transcript)
            agents[agent_id] = agent
            session.agent_id[agent] = agent_id
        for agent_id,spec in agentspec.items():
            agents[agent_id].subagents = {name:agents[sid] for name,sid in spec.subagents.items()}
        session.interlocutor = agents[interlocutor_id]
        session.next_message_id = max_message_id + 1
        try:
            session.next_agent_id = max(int(i) for i in agents.keys() if i.isdigit()) + 1
        except ValueError:
            pass
        return session




class TrackedString(str):
    """A string with logging metadata."""
    def __new__(cls, s, message_id):
        instance = super().__new__(cls, s)
        instance.message_id = message_id
        return instance

class MultiTrackedString(str):
      def __new__(cls, s, message_ids):
        if isinstance(s, MultiTrackedString):
            instance = super().__new__(cls, str(s))
            instance.message_ids = message_ids + [m for m in s.message_ids if m not in message_ids]
        else:
            instance = super().__new__(cls, s)
            instance.message_ids = message_ids
        return instance