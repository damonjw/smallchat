"""
LOGGING TRANSCRIPTS AND COMMUNICATION

Everything that is placed into a LLM transcript will be logged as
{message_id, content_id, event_type='transcript_entry', agent_id, role, content, caused_by?}

Sometimes it's useful to also log plain pieces of text. E.g. in the Discuss tool
the parent sends the same prompt to its subagents. The prompt doesn't appear in
the parent's transcript, but let's give it a content_id, so that the viewer app
can track all the things that this prompt caused:
{message_id, content_id, event_type='piece_of_text', agent_id, content, caused_by=<toolresult>}

What's the point of message_id AND content_id? Consider when an agent uses
the Discuss tool among subagents. It will send the same prompt to all of them,
and so each will get a transcript_entry with its own message_id, but the
content is the same in each case so they'll all have the content_id of the
original piece_of_text. The same applies when a response from one subagents is sent
to all the other participants. The content_id enables deduplication in the viewer app:
the viewer app knows it need only show a given piece of content once. We might as
well give every item in the log its own message_id, to make the viewer logic easier,
though there will be cases (e.g. user input to an LLM) where the message_id is never
referred to.

Thus, every string that is logged (every transcript entry, and every piece_of_text) 
will be given a globally unique content_id. To facilitate logging code,
we'll use the LoggedString class, which extends str but also stores content_id
and message_id and optionally caused_by. This way, code can pass around LoggedString objects
and (except for logging code) treat them as normal strings.

The role=user messages in an LLM transcript all come from *somewhere*, perhaps some other
agent's output, perhaps a piece_of_text from a parent agent. These logged transcript
entries will all have the caused_by field set, equal to the source's message_id. The other
transcript entries (role=assistant, role=tool) have caused_by left blank, to signify
that the cause is the agent itself.

An utterance is any LLM result that's just text without any tool call. An
utterance is returned to the parent agent (or to the ultimate end-user) as
a text string. It may be compiled into the parent agent's role=tool message,
and it may also be sent to other agents in a role=user message. Since it is
by definition an LLM result, it's in the transcript of the agent that produced it, 
and so it has a message_id.
- If the parent makes some minor formatting changes to the utterance, for example changing
  agent Jack's utterance "hello" into the string "[Jack]: hello", then
  the formatted string will be given the same content_id as the original utterance.
  This makes it easy for a viewer app to detect things that are "morally"
  the same, such as when an utterance is broadcast to several agents.
  (We don't need piece_of_text for this. The formatted string will appear in
  the recipient's transcript anyway, so the logs preserve the ground truth.)
- If the utterance is significantly changed in processing, it can be
  a new content_id with caused_by set to the original utterance.

LOGGING AGENTS THEMSELVES

Every agent that is created will be given a globally unique agent_id.
There's typically a tool call that causes agent creation,
{message_id, event_type='transcript_entry', role=assistant, tool_use=...}
The agent that is created will be logged as
{event_type='agent_created', agent_id, caused_by=<toolcall>, name, language_model}

There is no need for agent deletion events. An agent may choose to remove a subagent,
but that subagent can be seen as persisting indefinitely, just no longer linked to
by any other agent.
"""

class LoggedString(str):
    """A string with logging metadata. Use this to tag LLM inputs and outputs."""
    def __new__(cls, s, content_id, caused_by=None):
        instance = super().__new__(cls, s)
        instance.content_id = content_id  # every logged string gets a content_id
        instance.caused_by = caused_by    # optional
        return instance