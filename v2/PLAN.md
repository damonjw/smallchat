# Rewrite Plan: Agent-World Architecture

## Overview

This overview documents the high-level architecture of a
re-implementation of the mini-agent system.  Details about types and
message formats are not relevant at this stage of design. I am not
interested in compatability with the existing codebase, nor with
migration from it.

This plan follows classic AI architecture, consisting of an Agent and
a World. The Agent is the only thing in this system that makes
decisions.  It *uses* a LanguageModel to do its reasoning, but it's
the Agent that invokes actions. Tools are passive, like hammers --
they have no agency of their own, they just do what they're told and
they give feedback to the Agent that invoked them.

The design goal is to make it clear how an Agent's decision making works.
I want to get rid of the mysterious 'hooks' in the existing codebase,
and make all the behaviour explicit, so that anyone reading the Agent can see
exactly how its decisions are arrived at.

The main classes are:
- **LanguageModel**: processes a prompt text and produces a response text. Used as the reasoning engine
  by an Agent.
- **World**: models the environment in which the Agent lives. It represents 'physical' things like
  files. The Agent can 'perceive' the state of the world. The World also includes the user -- the action
  of requesting user input is an action on the World, resulting in a response.
- **Tool**: consists of an action to be performed on the World, possibly returning a perception of the result,
  and also an interface describing to the Agent what the Tool does.
-- Tool execution errors are
  treated as results. For example, if a filesystem action returns an error, then the Tool will wrap it up
  as a content block describing the error, and return it to the Agent as the result. This allows the Agent
  to decide what to do next, when it passes the error-content on to the LanguageModel.
- **Agent**: Makes all the decisions, i.e. orchestrates everything. It maintains a Transcript recording the conversation so far.
  It uses a LanguageModel to decide what actions to take next. It decides on system prompts and reminders,
  and injects them into the Transcript whenever it decides is appropriate.

Some ways in which an Agent interacts are
* To get a LLM response: `next_action = await language_model.response(prompt)`
* To invoke a tool and get the result: `result = await world.result(tool)`
* To run a subagent: `result = await self.subagent(prompt).response()`

(These are all async, in the same way that the existing codebase has them async.)

The LanguageModel is a passive entity that operates on text and returns text. It doesn't need any state,
beyond what limited state might be useful for system purposes such as maintaining a connection or a token,
but it's fundamentally functional.

As a general guideline, the Agent + LanguageModel represent all the things that might go on
inside the head of a human. The World represents everything in the world that a human interacts with.
The Tools are how a person interacts with the World. In more detail,


* The Agent invokes Tools, and the Tools then act on the world. This is similar to how a person (agent)
would use a hammer (tool) to act on the world (plank of wood and nail).

* The Transcript is part of the Agent's state. It's not part of the World because (according to the
human analogy) the Transcript is something that's part of a person's thought processes. The World
has a state, and it doesn't remember its history. (We won't bother with recording transcripts to a file.)

## The Update Step

In each update step, the Agent will invoke the LanguageModel, and then it will decide on an action
specified by what the most recent LanguageModel response says. There
are three types of action:
- Pure *cognitive* actions affect the state of the Agent. This might mean specifying extra text
  to be added to future LanguageModel interactions. It might mean modifying the current Transcript.
  The point is, they have no effect per se on the state of the world. They only affect the manner in which
  the LanguageModel is invoked, which has a consequence for future actions.
- Pure *physical* actions read or modify the state of the World. This might be running a bash command, or
  modifying a file. The action affects the current World, and it returns a result (either a report on the
  action's outcome, or a message describing an error which happened when the action was performed). The
  Action has no effect on the future of the Agent, other than via this message, and via the impact on the World.
- There are *hybrid* actions, which consist of first acting on the World, and second updating the state
  of the Agent based on the response. An example is ExitPlanMode, which first prompts the user
  (i.e. acts on the World, since user input is part of the World), and then modifies the Agent's
  state based on the result.

Here are some examples.
- Task is a cognitive action, since its effect is to create a subagent, and this has no effect
   on the World (other than what the subagent decides to do).
- Entering plan mode is a cognitive action, since its direct effect is only on the Agent's transcript
  but not the world. Likewise, explicitly turning plan mode off.
- NotebookEdit and Grep are physical actions, since they act straightforwardly on the World
  and return a result or error message to the Agent.
- MCP tools can provide pure physical actions.
- MCP tools can also provide system prompts, which are pure cognitive actions -- they simply add
  a system prompt to the transcript.
- ExitPlanMode is a hybrid action, since it involves prompting the user then possibly updating the
  Agent's state.
- We can even think of the initial system prompt and initial info about the environment
  as a simple cognitive action, if we like, though it doesn't get us anywhere!

For a pure physical action, perform the action on the World, and get the result, then append
the result to the Transcript. (This includes most MCP tool use, making this very flexible and extensible.)

For a simple cognitive action consisting of just a system prompt, append this to the Transcript.
(This includes MCP commands, making this very flexible and extensible.)

For a complex cognitive action such as entering plan mode, there will be bespoke code to achieve
the desired effects on the Agent's state. There are too many possibilities for complex cognitive actions
for it to be worthwhile trying to build a general-purpose architecture. Instead, we'll implement these
as needed inside the Agent class. 
(With bespoke Agent code, complex cognitive actions are obviously flexible, but it requires
custom work to do the extension. In future, when we've learnt more patterns, we can revisit this.)

For hybrid actions, again there needs to be bespoke code. The only example in the existing
codebase is ExitPlanMode. In the future, if we come up with more hybrid actions, we may
revisit this and come up with a more general pattern, but for now it's premature to generalize.
(With bespoke Agent code, hybrid actions are obviously flexible, but it requires custom work
to do the extension. In future, when we've seen more than one example, we can revisit this.)

### Example: websearch

The websearch tool is really an assistant Agent. Its starting instructions are "Run a query using the
ddg tool, to get a list of results. Then for each of them, ask a Digest agent to process it.
Then assemble all of the digests and ask the Combine assistant to combine them."

Assistants are just regular Agents. Like any agent, they can invoke tools and spawn subagents.
An agent is specified by its directives, and it can be given content to work on.
There are also behavioural agents ("Neuroses") which aren't given one-shot content; instead
they're given peeks at an ongoing content stream.



## The World Model

The World is a wrapper for all the means by which the Agent can interact with things that can
be deemed to have independent existence outside itself.
This includes getting user input, reading and writing files, and searching the web. In a larger
system it would include monitoring real-world sensors such as cameras.

The World consists of two sub-objects, a WorldModel (which has a state capturing the Agent's
  current understanding of the world including known_content_files) and an RealWorld (which mirrors the
  actual phsyical world, including the filesystem -- as an object in the codebase it's stateless, but the
  real physical world underneath obviously has state, and which also maintains a list of tools and
  connections to MCP servers). This World object will support `subworld = world.newmodel()` which will
  retain the RealWorld but provide a new empty WorldModel.

It's work discussing file-tracking in detail, i.e. known_content_files and stale_content_files. These will
be implemented as follows:
* The World keeps track of known_content_files in its WorldModel, and tools like Read and Grep record which
  files they access.
* The Agent or subagent, before each LanguageModel interaction, calls World.list_modified_files() to see which
  files have changed since last read, and uses this to craft a system message.
* A subagent will have its own World object, created with `subworld = world.newmodel()`. This will
  share the RealWorld object of its parent Agent, but have its own fresh WorldModel.
  This will mean that, even when multiple subagents are editing files, each subagent or agent
  is looking at the same filesystem, and keeps track of which files have been modified by
  someone else in the interim.

