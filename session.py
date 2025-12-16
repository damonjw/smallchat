"""
GOALS

The logging infrastructure is designed to allow (1) suspend / resume sessions,
(2) extract various views of agent interactions, e.g. "show just the dialog between
these three agents".

DESIGN PRINCIPLES

Event sourcing: we can reconstruct the entire state of the system
by replaying the log i.e. the event stream. The state consists of
- the set of all agents
- the subagent relationships between them
- the interlocutor, i.e. who the end-user is speaking with
- the metadata of each agent
- the transcript of each agent
- TODO: to support suspending in the middle of operations, we should also
  be able to reconstruct which agents are waiting for input. For this version,
  we'll only support suspending and resuming while waiting for end-user input.

In the architecture, operations (Agents, response loop, transcripts) should be primary,
and logging (Session) should be an add-on. In other words, it should be possible to 
remove all logging code from the Agent, and the operations would still run correctly;
and furthermore logging shouldn't require changing the function signatures for Agent.
The existing code very nearly manages this -- the only violation is that the Agent
constructor includes a handle to the Session, in order for it to even be able to run
the logging commands provided by Session.

Session maintains a list of all the agents. It is in charge of allocating IDs
to agents and messages. It provides logging commands, which add entries to the
log.

Agents are responsible for invoking the log commands. Principally this is to record
additions to the transcript. There are a few extra logging commands offered:
- Session can log fragments of text. This is useful for establishing semantic
  linkages between transcript entries, so they can be displayed in the viewer.
  It's mostly relevant for detailing communication, in the Discuss tool.
- Session can log agent creation. This is useful for establishing the relationships
  between agents. It's redundant -- agents are only created by the Task tool, so
  the same information could be obtained by parsing tool-use transcript entries --
  but it's cleaner if the Session resumption / Viewer code doesn't have to know
  the internals of tools.


LOGGING TRANSCRIPTS AND COMMUNICATION

Formally, everything that is placed into a LLM transcript will be logged as
{message_id, event_type='transcript_entry', agent, role, content, ...}

It's worth recalling the different types of transcript entry:
- {role:user}: these are the inputs to an agent
- {role:assistant, tool_calls:[]}: these are "utterances" by the agent
- {role:assistant, tool_calls:[...]} or {role:tool}: these are for too use by the agent

For semantic tracking in the viewer, it's also useful to be able to log plain
fragments of text that are produced by an agent but *don't* appear in that agent's
transcript. For example, consider the Discuss tool, in which the parent sends
the same prompt to one or more of its subagents. The prompt doesn't appear in
the parent's transcript, but let's give it a message_id, so that the viewer app
can track all the things that this prompt caused:
{message_id, event_type='fragment', agent, content, ...}

For semantic processing in the viewer, and to enable navigation in the viewer, 
it's also useful to denote logical dependencies between logged items. There are 
two types of dependency that the log records capture:
- If one logged item X is substantially the same as another Y, and if X came first, 
  then Y will have {..., substance=X_message_id}.
- If one or logged items X1,...,Xn were processed to produce Y, but it's not
  substantially the same, then Y will have {..., cause=[X1_message_id,...,Xn_message_id]}.
  Causes may also have the form "X1_message_id.tool_call_id" to indicate that the cause
  is a specific tool call. If the list is only one item long, it may be
  simplified to a string.
- It doesn't make sense to have both substance and cause set.
  Setting substance=X implies that the message in question was caused by X --
  how else could the message have the same substance as X if X did not precede it? --
  and so it's redundant to also set cause.

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
  - If the tool returned a StringWithCause(cause=Z), that means it's a string that has been
    composed out of one or more other strings. Store {..., cause:Z} to record this fact.
    
- Consider an utterance {msg_id=X, role=assistant, content="hello"} from a subagent.
  The parent may make some minor formatting changes to the string, e.g. 
  change it from TrackedString(msg_id=X, content="hello") to TrackedString(msg_id=X, content="[Jack]: hello"},
  keeping the msg_id unchanged. This way, when it's sent to another agent, that other
  agent will correctly record a transcript_entry with substance=X.
  The parent might also compile the string into its tool-result transcript entry,
  in which case it will specify that the transcript entry has cause=X.
  (We'll also allow cause to be a list, to allow for a tool-result that compiles multiple messages.)


To facilitate logging code, we'll use the TrackedString class, which extends str but also
stores message_id. This way, code can pass around TrackedString objects
and (except for logging code) treat them as normal strings. For tool results, which
may have multiple causes, there is StringWithCause.


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
        assert name is not None, "Agents must be named"
        agent_id = self._make_agent_id(agent=agent, base_name=name)
        log = kwargs | {'event_type': 'agent_created', 'agent': agent_id, 'name': name, 'parent': self.agent_id[parent], 'language_model': agent.language_model}
        return self._write(log, required=self.AGENT_CREATED)

    def _make_agent_id(self, agent, base_name):
        base_agent_id = ''.join(c if c.isalnum() or c == '_' else '_' for c in base_name.lower()).strip('_')
        agent_id,i = base_agent_id,1
        while agent_id in self.agent_id.values():
            agent_id = f"{base_agent_id}{i}"
            i = i + 1
        self.agent_id[agent] = agent_id
        return agent_id        

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
        return session




class TrackedString(str):
    """A string with logging metadata."""
    def __new__(cls, s, message_id):
        instance = super().__new__(cls, s)
        instance.message_id = message_id
        return instance

class StringWithCause(str):
    def __new__(cls, s, cause):
        instance = super().__new__(cls, s)
        instance.cause = cause
        return instance