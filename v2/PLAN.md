# Rewrite Plan: Agent-World Architecture

## Goals

This overview documents the high-level architecture of a
re-implementation of the mini-agent system. The goal is to be a research platform
for investigating agentic behaviours.
- Note that the existing codebase is also just a research demo, and it has no users.
  So there is no concern about migration.
- This is a high-level design. Details about types and
  message formats are not relevant at this stage of design. I am not
  interested in compatability with the existing codebase, nor with
  migration from it. It will be a complete re-implementation from scratch.

**Research goal: explore complex agentic behaviours.** The main goal is to explore complex agentic behaviours. 
I think it's worth exploring different ways that agents might work, for the following reasons.
- Claude Code is a clever and useful system. The existing codebase shows that Claude Code
  is nothing more than a generic agent system with subagents and hooks. This redesigned architecture
  looks deeper at these features. It keeps subagents pretty much as-is (and calls them Tasks) and has a cleaner 
  implementation (rather than e.g. the current websearch behaviour is fragmented across the codebase). And it 
  generalizes hooks (and calls them Compulsions), and gives them greater expressive power.
- This rewrite tries to achieve a system reminiscent of Smalltalks live-coding environment.
  Nearly all behaviours are controlled by written text, which the user can inspect and modify.
  (In this design, we think of written text as "code" and the LLM as an "execution engine". Users can extend 
  the system by writing new "code" in the form of new agent and tool descriptions.) Such a live-coding
  environment is good for research. In contrast, the existing codebase doesn't permit us to experiment and 
  tweak without editing code.

**Concrete use cases.** 
- At the moment, users open multiple terminals with different Claude Code sessions,
  each with a different system prompt, and they cut-and-paste between them. With this redesign, it will 
  be trivial for the user to tell the agent "I want you to look at this problem from multiple viewpoints",
  and to specify those viewpoints. Further, the agent could be given a general instruction: "If it looks
  like this is a hard problem, or if you're disagreeing with the user, then set up a viewpoint advocating for
  the user so that you can make sure your points aren't easily rebutted."
- This architecture is not meant to be limited to coding assistants. It's meant as a general
  platform for all sorts of AI-assisted work, such as research, literature scanning, and other
  types of thinking and tool use. The live-coding aspect of this design makes it easier to
  explore different types of agentic behaviour for these tasks.

**Complexity versus flexibility.** 
This rewrite has tried to identify the fundamental 
primitives of how agentic systems operate. The hope is that with just a few primitives we can have a rich system
with very few limits to what's possible. This should allow us to have a very simple *implementation*, with
complex *emergent behaviour*.
- This is meant as a research experiment, not a production system. If we can get great complexity with a tiny number
  of primitives, then it's great for research.
- Several parts of the current design are fragmented across the codebase. For example, look at the system for planning mode, 
  or for web search; in this redesign they will be unified. Also, the current codebase has two separate agentic loops;
  in the redesign there will be just one. I claim that the redesign will reduce implementation complexity.
- Will it be impossible to debug? I think that "debug" is the wrong idea here. The hope is to design
  a system in which complex autonomous conscious-like behaviour can emerge. Simple engineering ideas
  about "debugging" simply don't apply to complex emergent systems. I can't "debug" a 
  human collaborator! The redesign should have full logging of transcripts of course, but I expect they won't
  be very helpful.

**Performance versus flexibility.** This new architecture is considerably more flexible than the existing codebase.
Will this lead to performance problems? I claim that the new system
is able to regulate itself using emergent behaviour rather than hard-coded limits.
- There could be a Compulsion that's 
  set up to watch for excessive spawning of subagents of various types, which it could then block.
- If a discussion among Viewpoints goes on too long without getting anywhere, a Compulsion could
  spot this and tell the agent to close the discussion.
- Note that the existing codebase does have recursive complexity (agents can spawn subagents, which can
  then spawn subagents themselves), and that it doesn't have any mechanisms for limiting this!





## Architecture

This plan follows classic AI architecture, consisting of an Agent and
a World. The Agent is the only thing in this system that makes
decisions.  It *uses* a LanguageModel to do its reasoning, but it's
the Agent that invokes actions. Tools are passive, like hammers --
they have no agency of their own, they just do what they're told and
they give feedback to the Agent that invoked them.


The main classes are:
- **Agent**: Makes all the decisions, i.e. orchestrates everything. It maintains a Transcript recording the conversation so far.
  It uses a LanguageModel to decide what actions to take next. It decides on system prompts and reminders,
  and injects them into the Transcript whenever it decides is appropriate.
- **World**: models the environment in which the Agent lives. It represents 'physical' things like
  files. The Agent can 'perceive' the state of the world. The World also includes the user -- the action
  of requesting user input is an action on the World, resulting in a response.

The core Agent loop is to repeatedly perform these two steps:
1. Ask the LanguageModel to produce one or both of TextContent and Action, given the current Transcript.
   - If the LanguageModel doesn't specify an Action, then the agent will use its default Action.
     For the primary agent, the default Action is *request_input*.
   - There are some subagents discussed below, Task and Viewpoint and Compulsion.
     They have different default Actions, because they are used in different ways.
   - The LanguageModel doesn't need to know anything about these default actions. The default
     actions are used purely for control flow.
2. Perform the Action, and get the result. The TextContent, the Action, and its result are all added to the Transcript.
   - The *request_user_input* Action will show the TextContent to the user, then ask the user what to do next.
     The user's reply becomes the result of the action.
   - The *tool_use* Action instructs the agent to invoke a tool. The Action includes the specification of
     the tool, including its name and arguments. If the tool name is one of the tools the Agent knows about
     for acting on the World, then it invokes the tool and returns its output as the result.
   - Tool execution errors are treated as results. For example, if a filesystem action returns an error,
     then it will be wrapped up as a content block describing the error, and returned to the Agent as
     the result. This allows the Agent to decide what to do next, when it passes the error-content on
     to the LanguageModel.
3. In most cases, we then loop back to the first step. (There are two exceptions, relating to subagents,
   described below.)

(The two steps, invoking a LanguageModel and invoking a tool on the World, are both async.
This mirrors the existing codebase.)

In this way, the agent can perform a loop consisting of user input, LanguageModel responses, and tool use.
There are however some special Actions that have the effect of modifying this basic loop. These special actions
are associated with Tasks, Viewpoints, and Compulsions. They are described below.

As a general guideline, the Agent + LanguageModel represent all the things that might go on
inside the head of a human. The World represents everything in the world that a human interacts with.
The Tools are how a person interacts with the World. In more detail,
- The LanguageModel is a passive entity that operates on text and returns text. It doesn't need any state,
  beyond what limited state might be useful for system purposes such as maintaining a connection or a token,
  but it's fundamentally functional.
- The Agent invokes Tools, and the Tools then act on the world. This is similar to how a person (agent)
  would use a hammer (tool) to act on the world (plank of wood and nail).
- The Transcript is part of the Agent's state. It's not part of the World because (according to the
  human analogy) the Transcript is something that's part of a person's thought processes. The World
  has a state, and it doesn't remember its history. (We won't bother with recording transcripts to a file.)


### Tasks

A Task is a subagent, created to perform a specific task. In programming terms, it's like invoking a function.

In more detail: The *task* Action initiates a new subagent to perform a task. This Action specifies the template to
use as the system prompt for the subagent, and the prompt to give it. The subagent then runs its 
own agentic loop. The subagent will use a default action *done* which has the meaning "break 
from this agent's loop, and return the latest TextContent as the result". To
invoke the Task, the primary agent calls `result = await subagent.response(prompt)`.

A subagent is similar to a tool, in that it can be invoked and it returns an answer. It's richer than
a simple World-modifying tool because it's powered by a LanguageModel and it has the ability to spawn its own subagents.

A Task can in principle ask the user for input, if it has been given access to the *request_input* tool.
This is similar to how I (the user) might ask someone for help, and they might hand me off to a subordinate.

**Example: websearch.** The websearch tool is really just a Task. Its starting instructions are "Run a query using the
ddg tool, to get a list of results. Then for each of them, ask a Digest agent to process it.
Then assemble all of the digests and ask the Combine assistant to combine them."


### Viewpoints

A Viewpoint is another subagent. The difference between a Task subagent and a Viewpoint subagent is that 
the Viewpoint runs persistently, and there can be several Viewpoints. In programming terms, it's like
starting several threads.

In more detail: The *viewpoint* Action initiates a new subagent. This Action specifies the template to use
as the system prompt for the subagent, and a name. The primary Agent can add to this subagent's Transcript
by calling `viewpoint.notify(message)`. It asks the subagent for a response by `comment = await subagent.response()`.
The primary Agent can also terminate a Viewpoint with the Action *discard*, specifying the name of the viewpoint
to terminate.

The primary agent can use several Viewpoints as a way of holding a dialog between different points of view.
It does this whenever it has the Action *consider(prompt)*. This action will send the prompt to each Viewpoint.
Each Viewpoint in turn is asked for a comment, and the comment is notified to all other Viewpoints.
The comments are shared as messages with role="user" and content="[agent_name] comment-contents".
This way the different Viewpoints know who said what. The Viewpoints may also receive messages
role="system" and content such as "agent_name has left the chat", so that they're aware of who is participating.
The Viewpoint's system prompt will include instructions explaining all this.
The result of this *consider* Action will be a list of messages from the Viewpoints who responded.

When we call `subagent.response()`, the subagent runs its own agentic loop. It has the default Action *done*.
As with the Task, this Action means "break out of the loop, and return the most recent TextComment as the response".
In this way, a Viewpoint has the autonomy to act as a full-fledged agent, for example by using subagents or tools.
And it persists until the primary agent decides to remove it.


### Compulsions

Compulsions have a similar role to hooks in the current codebase. They modify the primary agent's loop.

A Compulsion is just another agent. It is created by specifying a template to
use for the system prompt, plus any further prompt that's needed. The primary agent may have several Compulsions.

In the primary agent's main loop, its Compulsions are given two chances to intervene: before invoking the LanguageModel,
and before performing the Action. 
- Before invoking the LanguageModel, i.e. after receiving the result of the previous Action, we
  call `message = await compulsion.response(result)`. If this returns a non-empty message, it's added to 
  the transcript. 
  - This corresponds to `UserPromptSubmitHookAdditionalOutput.additionalContext` in the existing codebase.
    In this revised design we don't distinguish between hooking into UserPrompt versus hooking into PostToolUse,
    since user prompt is just another tool use.
- Before performing an Action, i.e. after receiving the Action from the LanguageModel,
  we call `result = await compulsion.response(action)`. The result may be either empty (meaning that
  the Agent can go ahead and perform the Action), or a non-empty result (meaning that the
  Agent is prevented from performing the Action, and this result will explain why).
  - This corresponds roughly to `PreToolUseHook` in the existing codebase.

In this way, each Compulsion is given the opportunity to provide further instruction to the primary Agent
(for example to remind it to use the TodoWrite tool). And it's also given the opportunity to constrain
how the primary Agent can use Tools (for example, telling it not to report back to the user until it's considered
its response from multiple viewpoints). A Compulsion could use this, for example, to ensure that 

Inside the Compulsion's agentic loop, the default Action is *done*, which works as for a Viewpoint.
As with Viewpoints, this means that the Compulsion can act as a fully-fledged Agent, for example launching its 
own subagents. There is also a special Action *quit* which also breaks out of the loop, and which 
instructs the primary agent to terminate this Compulsion.

There fundamental difference between a Compulsion and a Viewpoint is this. A Viewpoint is under the control
of the primary agent: the primary agent has full control about when to invoke it. But a Compulsion is
not under the control of the primary agent: the Compulsion always acts if it wants to, and only the Compulsion can
decide to terminate.

The existing hooks for planning_mode, TodoReminder, and have_read_files_watcher will all be implemented 
as Compulsions. The only other hook in use at the moment, the InitialMessages.initial_hook, will not be Compulsion since
it's only needed at the beginning of the session. These are all Compulsions, since the primary agent does not
have the authority to terminate them.

The primary agent can create a new Compulsion using the *compulsion* action, specifying the template and
any additional prompt. For example, there could be an existing Compulsion that watches out for cases where
the user repeatedly corrects something that the primary agent says. When it sees this, it can insert a system message
to tell the primary agent "You should consider creating a compulsion to watch out for this." This is similar
to how we can train a cat not to jump on counters: spray it with water whenever it does so, and it will eventually
gain a Compulsion to avoid that behaviour.





### Interlocutor control

Initially, the user is talking with the primary agent. But if the primary agent initiates a Task and tells the task
to run its agentic loop with the default action *request_input*, then all of a sudden the user is talking with the subagent.
We can also imagine simple mechanisms by which the user could talk to a Viewpoint or a Compulsion, if they want.



### The World

The World is a wrapper for all the means by which an Agent can interact with things that can
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

Arguably, this design is cleaner than the existing mechanism with a global state for `known_content_files`.
In the existing codebase, if there are several subagents then they may end up with inconsistent knowledge.
Specifically, suppose agent A reads a file, then spawns subagent B who edits the file then terminates,
and that agent A then edits the file. In the current system, the global variable will say that "we" know
about the edit, and therefore agent A will be permitted the write -- when in fact agent A is unaware.
This WorldModel redesign avoids this inconsistency, since each agent has its own WorldModel that tracks
which files it has read.
