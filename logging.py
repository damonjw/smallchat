"""
LOGGING TRANSCRIPTS AND COMMUNICATION

Everything that is placed into a LLM transcript will be logged as
{message_id, event_type='transcript_entry', agent_id, role, content}

Sometimes it's useful to also log plain pieces of text. E.g. in the Discuss tool
the parent sends the same prompt to its subagents. The prompt doesn't appear in
the parent's transcript, but let's give it a message_id, so that the viewer app
can track all the things that this prompt caused:
{message_id, event_type='piece_of_text', agent_id, content, cause}

These two objects may also have a substance field or a cause field (but not both).
If substance is set, it's a message_id. If cause is set, it may be either a message_id,
or a {message_id,tool_use id}, or a list of message_ids.
- substance: means that the item is essentially the same as another piece of text
- cause: means that the item was triggered by some other, but it's not the same

To illustrate, here are some examples.

- Consider when an agent uses the Discuss tool among subagents. It sends the same prompt
  to all of them. It creates a {msg_id=X, event_type=piece_of_text, content=prompt, cause=...}, 
  and sends it to each of them, and each of them creates a transcript_entry with substance=X.

- Likewise when a response from one subagent is sent to the other participants, 
  there will be an original {msg_id=X, event_type=transcript_entry, ...} from the
  subagent who's speaking, and this will result in a transcript_entry with substance=X
  in each of the other participants.

- When a piece_of_text is created, it is created as the result of the agent's tool use.
  Let's say the tool use is {message_id=X, event_type='transcript_entry', role=tool, ...}.
  The piece_of_text will have cause=X, to indicate that it was created as a consequence
  of the tool use, but it does not have the same substance.

- The role=user messages in an LLM transcript all come from *somewhere*, perhaps some other
  agent's output, perhaps a piece_of_text from a parent agent. These transcript entries
  should all have substance set, and it should point to the input message.

- Define an *utterance* to be any LLM result that's just text without any tool call. An
  utterance is returned to the parent agent (or to the ultimate end-user) as
  a text string. Since it is an LLM result it's in the transcript of the agent that produced it,
  so it has a event_type=transcript_entry log, with a message_id.
  The substance field is blank, since it is by its nature a novel string.
  We'll also leave cause=blank, to indicate that the cause is the LLM's entire transcript.

- Consider an utterance {msg_id=X, role=assistant, content="hello"} from a subagent.
  The parent may make some minor formatting changes to the string, e.g. 
  change it from LoggedString(msg_id=X, content="hello") to LoggedString(msg_id=X, content="[Jack]: hello"},
  keeping the msg_id unchanged. This way, when it's sent to another agent, that other
  agent will correctly record a transcript_entry with substance=X.
  The parent might also compile the string into its tool-result transcript entry,
  in which case it will specify that the transcript entry has cause=X.
  (We'll also allow cause to be a list, to allow for a tool-result that compiles multiple messages.)

The substance and cause fields will be used by the viewer, to enable deduplication
and tracing of linkages. Setting substance=X implies that the message in question was 
caused by X -- how else could the message have the same substance as X if X did not precede it? --
and so there should never be any case where both substance and cause are set.

To facilitate logging code, we'll use the LoggedString class, which extends str but also
stores message_id. This way, code can pass around LoggedString objects
and (except for logging code) treat them as normal strings.


LOGGING AGENTS THEMSELVES

Every agent that is created will be given a globally unique agent_id.
There's typically a tool call that causes agent creation,
{message_id=X, event_type='transcript_entry', role=assistant, tool_use=...}
The agent that is created will be logged as
{event_type='agent_created', agent_id, cause=X, name, language_model}

There is no need for agent deletion events. An agent may choose to remove a subagent,
but that subagent can be seen as persisting indefinitely, just no longer linked to
by any other agent.
"""

class LoggedString(str):
    """A string with logging metadata. Use this to tag LLM inputs and outputs."""
    def __new__(cls, s, message_id):
        instance = super().__new__(cls, s)
        instance.message_id = message_id  # every logged string gets a message_id
        return instance