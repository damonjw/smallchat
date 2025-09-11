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

### Research goal: explore complex agentic behaviours.

The main goal is to explore complex agentic behaviours. 
I think it's worth exploring different ways that agents might work.
We have seen from Claude Code that some agentic cleverness can turn a conventional
LLM agent into a fantastically useful assistant. The existing codebase is a proof of concept
that Claude Code can be seen as a generic agent system with two extra mechanisms that affect
the agentic loop: subagents, and hooks.
This redesigned architecture is intended as a platform for exploring what can be achieved
with further mechanisms.

This rewrite tries to achieve a system reminiscent of Smalltalks live-coding environment, in that
nearly all behaviours are controlled by written text, which the user can inspect and modify.
This should allow for rapid prototyping of new features.
Note that this platform is meant to be used for all sorts if AI-assisted work,
such as research, teaching, writing, and many other sorts of thinking -- it's not meant to
be limited to coding assistants. Claude Code (and the existing codebase) have certain agentic
behaviours that are useful for a coding assistant, but this platform is meant to be general enough
to help us explore what sort of agent behaviours would be useful in other scenarios.
That's why a Smalltalk-style live-coding environment, in which the user can specify new
mechanisms just by giving a text description, is so useful.

Here are some use cases:

- **Debate.** 
  At the moment, users of Claude Code open multiple terminals with different Claude Code sessions,
  each with a different system prompt, and they cut-and-paste between them. This allows them to get 
  multiple perspectives on their code. With this redesign, it will be trivial to achieve this, and
  we'll be able to experiment with different ways of managing the debate by tweaking the system prompts
  used by the agent who starts the viewpoints.
- **Resource constraints.**
  At the moment, the system has potentially unbounded complexity: Claude Code (and the existing codebase)
  allow multiple subagents to be spawned in parallel, and each subagent can recursively spawn more subagents.
  It's natural to be worried about this, and to want to explore ways to constrain resource use.
  In the existing codebase, we'd have to code our own hooks to achieve this. In the redesign, we 
  can simply tell the agent to create a Compulsion that monitors subagent creation, and blocks it when 
  appropriate. It's much simpler that coding our own hooks, and it's more expressive because it has
  the full power of a language model behind it.
- **Steel man reasoning.**
  We could for example create a Compulsion that reminds the agent: "if you're disagreeing with the user,
  then set up a viewpoint advocating for the user's point of view so that you can make sure your points
  aren't easily rebutted." This would make for a better experience for precise-minded users, like myself.
  It would be very fiddly to achieve this in the current system of hooks and tasks, but it'd be trivial
  to achieve this in the redesign, just by giving textual expression.


### The cost of flexibility?

The intention behind this architecture is that it should have just a few primitives that are simple to *implement*,
and which allow for very complex and sophisticated *emergent behaviour*. This is meant as a platform for exploring 
possibilities, not a production system. If we can get great complexity with a tiny number
of primitives, then it's great for exploration.

At its core, this new architecture has just two primitive entities: Agents, and World. Agents can be used in different
ways to achieve different functionalities.
- Obviously, the main agentic loop is an Agent.
- The existing codebase uses hooks. In this new architecture, hooks are implemented as Compulsions, which are
  nothing more than Agents. In other words, we've done away with some primitives, and we've made it easy
  to create hooks that have greater expressive power.
- The existing codebase already uses agents for Tasks. In the new design there is a slight generalization to
  Viewpoints, which are basically just Tasks with more flexible lifecycle management. (The new design keeps Tasks
  for convenience, but they could be implemented as Viewpoint agents if we wanted.)
- In the existing codebase, the functionality is fragmented across multiple parts, and it's hard to follow the
  execution flow. I believe that the redesign will reduce implementation complexity.
  - Consider for example websearch, which involves a fiddly division of responsibility between the tool
    and the main agent loop; in the redesign it will just be a Task with an appropriately written system prompt.
  - Or consider the hook for Planning Mode, which currently involves a global state variable, callbacks in the main agent
    loop, and other code in hook handlers. In the redesign, it can be achieved as a simple Compulsion with an 
    appropriately written system prompt.

**Performance versus flexibility.** This new architecture is considerably more flexible than the existing codebase.
Will this lead to performance problems? There may be problems, just as the existing codebase has problems (see
the earlier discussion about resource constraints). It's well worth investigating resource issues and performance.
The virtue of this new architecture is that it's easy to trial different types of constraints,
simply by writing text to describe the constraints we want. This is an easier way to experiment than
by writing code! For example,
- To prevent a recursive explosion of Agents, there could be a Compulsion that's 
  set up to watch for excessive spawning of subagents of various types, which it could then block.
- To prevent excessive resource use by too many Viewpoints who argue too long without getting anywhere,
  there could be a Compulsion set up to spot the problem and tell the convening agent to close the discussion,
  deleting the Viewpoints and freeing up resources.
- There are also plenty of hard-coded limits that it would be trivial to add should they prove necessary.
  For example, we could make it so that Compulsion agents are not given access to the *compulsion* action:
  this would prevent recursive compulsions. This sort of hard-coded limit is trivial to add should it
  prove necessary, so there's no point building it in the first instance into a platform designed for exploration.

**Understandability versus complexity.** This new architecture might lead to emergent behaviours that
are very hard to understand. In part, that's a design goal -- to design a system capable of showing rich
and sophistcated behaviour. But we'll still want to be able to review what's going on, to try to
gain understanding of the emergent properties. So of course we should support full logging of transcripts.
I expect we'll need sophisticated ways to process these logs -- we won't get very far by simply reading them.

Note that "debugging" is the classic software engineering sense is not a helpful concept here. This will be much
more like training a neural network image classifier: the code itself is straightforward (as I argued,
it has just two core primitives), but the behaviour
of the resulting system is complex. To "debug" what's wrong with a machine learning classifier we will
generally need statistical analysis, such as visualisation based on collections of many runs,
rather than traditional software-engineering style debugging. Likewise, to understand
the agentic systems I wish to explore here, it's likely that I will need to do data-science investigation of
collected logs. Thus,
* For the purposes of building the platform, what matters is that it should generate full logs of transcripts,
  so that we can see exactly what happened.
* For the purposes of analysis, we need our general data-science skills to make sense of these collections
  of logs. It's best practice in data science to start with exploratory analysis; it's premature to
  propose hypotheses or specific experiments until we have some understanding of the dataset.





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
     actions are used purely for control flow. The default actions aren't included in the transcript,
     since they can be easily inferred from context, without any ambiguity.
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

This core Agent loop allows for the conventional loop consisting of user input, LanguageModel responses, and tool use.
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

**Observability.** It's worth making a point about default actions. They're not recorded in the transcript in order to maintain
compatibility and LanguageModel functionality. But they can be trivially inferred from the transcript, for
the purposes of debugging and analysis. Let me explain in more detail:
- In existing agent systems, a transcript consists of alternating turns: there will be one or more messages with role="user"
  or role="system", then a message with role="assistant", then back to the user. It's implied by the role="assistant"
  message that what follows is either a tool use (if one was specified), or a prompt to the user (if no tool was
  specified). In other words, the existing setup does implicitly involve default actions that aren't recorded
  in the transcript.
- Existing language models have been trained to expect this sort of transcript.
- It is trivial to deduce from the transcript what the next tool use will be, even if that tool
  use isn't explicitly stated. For example, in the main agent, if an assistant message doesn't have an explicit
  too use then the implicit tool *must* be *request_input*. There is no ambiguity.
- More generally, we will maintain log files that record the type of each agent as well as its transcript.
  It will therefore be trivial to deduce from the logs what the implied actions are.
  There is no flexibility: a given agent type always has exactly the same default action.



### Tasks

A Task is a subagent, created to perform a specific task. In programming terms, it's like invoking a function.

In terms of implementation, it is simply an Agent. I'm just calling it a Task in this document to highlight
how it's used, not how it's implemented.

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

In terms of implementation, it is simply an Agent. I'm just calling it a Viewpoint in this document to highlight
how it's used, not how it's implemented.

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
A compulsion is created by specifying a template to
use for the system prompt, plus any further prompt that's needed. The primary agent may have several Compulsions.

In terms of implementation, it is simply an Agent. I'm just calling it a Compulsion in this document to highlight
how it's used, not how it's implemented. Since it's an Agent it's easy to specify complex behaviours simply
by writing text. In the current codebase, hooks are code, and to create a complex hook one has to write complex code.

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

The World object mirrors the actual phsyical world, including the filesystem. So as an object in the
architecture it's mostly stateless -- but the real physical world underneath obviously has state, and
the object mirrors this. The only parts of the World that need state are (1) connections to MCP servers,
which is part of the Env object in the current codebase, and (2) tracking of `known_content_files` 
as in core_tools in the current codebase.

When an agent creates a subagent, that subagent is given access to the same World object as the original agent.

It will also be possible to specify the actions that a subagent can use, as in the existing codebase. The World will
have all the tools; the Agent will have a field specifying which tools and actions are allowed. The subagent might be given 
access to all the parent agent's tools; the subagent might be given a filtered list of tools; or the subagent
template might specify additional tools that can be found on a specific MCP server.
- Example use case: if we want to prevent nested Compulsions, we can specify that a Compulsion should
  not be allowed to use the <compulsion> action, thereby preventing a situation of nested compulsions.


#### A possible race condition, and a fix

There is a potential race condition in the current codebase, which
the new architecture will copy. It's worth documenting this now, and considering how it might be
fixed. But the existing codebase seems to work well, so I don't see any need to build this fix
in the first instance -- let's wait until it's clear that the complexity is worth it. The problem 
is as follows:

1. The current codebase has global state variables for `known_content_files` and `stale_content_files`.
   It also permits multiple Task agents to operate simulatenously, via async / await.
2. The purpose of these global variables is to keep track of whether the Agent's transcript
   has the most recent copy of a file, or whether the file might have changed since.
   If there are changes, the hook can insert a reminder.
3. The race condition is this: there may be several Tasks spawned in parallel. If agent A
   reads a file, agent B reads then writes, then agent A writes, then agent A is writing
   without the most recent copy in its transcript. Because there's only a single global state
   variable, the hook isn't clever enough to know *which* agent has up-to-date knowledge 
   in its transcript.

We could fix this with two changes. (1) Let the World store per-agent state. When an agent spawns
a subagent, the subagent will get a fresh empty per-agent state. This will be used to keep a record
of per-agent `known_content_files`. (2) There's still a race condition, because the check of existing files
and the agent's action are executed asynchronously with async / await, and so a file might be changed
in between when the FileWatcher reports is findings and when the Agent performs a write action on a file.
This can be remedied in the standard way, by having timestamps or version numbers or checksums on the files in
`known_content_files`. -- The respective effects of these two changes will be to (1) provide more specific
system messages about which files have changed per agent, and (2) give a deterministic guarantee that
files can't be written unless they've first been read.

As discussed, the existing codebase seems to work well, so the potential race condition doesn't seem
to hurt in practice, and so in the first instance we won't implement the fix described here.