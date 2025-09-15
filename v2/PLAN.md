# New architecture plan

Note that this is a high-level design. Details about types and
message formats are not relevant at this stage of design. I am not
interested in compatability with the existing codebase, nor with
migration from it. It will be a complete re-implementation from scratch.

## TODO

If we have smart-agent hooks then they'll end up with a transcript as big as the main agent,
which seems like an awful lot. Maybe smart-agent hooks will only be useful if we can sensibly
trim the transcript. For the existing hooks at least, they don't need to keep much transcript at
all.

The area of long-term memory planning is something with lots of developments:
[Hacker-news discussion](https://news.ycombinator.com/item?id=45214908)
pointing to 
[Anthropic's description](https://www.anthropic.com/news/memory)
and
[ChatGPT memory and the bitter lesson](https://www.shloked.com/writing/chatgpt-memory-bitter-lesson)
and
[Claude memory](https://www.shloked.com/writing/claude-memory)

In brief,
- Claude externalizes the transcript into searchable data. For a hook, maybe we can treat the
  main agent's transcript as searchable data.
- Or the hook's transcript can be externalized, keeping only a small working transcript.
But I don't want to be in the business of keeping track with the latest developments in
a big field! All I should aim for is to be able to use others' ideas here,
and maybe make it easy to play around with a few of them if they fit into the
research agenda of multi-agents and hooks.


## Overview

This plan follows classic AI architecture, consisting of an Agent and
a World. The Agent is the only thing in this system that makes
decisions. The Agent acts on the World by invoking Tools, which return Results.

In a programming analogy, a Tool is like an API call: it's an atomic operation designed
to achieve a specific outcome. Whereas an Agent is like a piece of code: it embodies control
logic. More precisely, an Agent is similar to a generator or a lazy list: it's an object
that can repeatedly receive input and returns output. Formally, it is invoked using
`output = await agent.response(input)`.

An Agent might be dumb or it might be a SmartAgent. A dumb agent is specified by conventional code,
whereas a SmartAgent is specified by textual instructions, and powered by a LanguageModel that decides
how to act on its input according to those textual instructions.

A SmartAgent maintains a Transcript, and has a pointer to the World, and has access to a LanguageModel.
Its core loop is similar to the existing `agentic_loop` in mini_agent.py. In simplified form it looks like this:
```
async def response(self, input):
    while True:
        (text_content, action) = await self.language_model.complete(self.transcript)
        transcript.append(text_content)
        if action is None:
          return text_content
        result = await self.world.do_action(action)
        transcript.append((action, result))
```
Some more considerations about smart agents:
- The two steps, invoking a LanguageModel and invoking a tool on the World, are both async.
  This mirrors the existing codebase.
- The agent's World keeps track of which actions it's allowed to perform (and as in the current codebase this might be customized
  for subagents.)
- Actions might timeout or raise exceptions, exactly as in the existing codebase. We'll take the
  same approach to dealing with them. Specifically: if there's a problem performing the action,
  the problem is converted to a text string or strings, and this is then bundled up into a Result
  that the LanguageModel sees next time round the loop. The output of the `response` function
  is only ever text, not error objects.

**Exceptions.** What if it's a dumb agent and its response function throws an exception?
Or what if in a smart agent there's a failure with the LanguageModel call itself?
I think the simplest design is to insist on trapping all errors: the LanguageModel.response
command can invite the user to retry (as in the current codebase), and anyone writing
a dumb agent should be instructed to trap all exceptions. On the other hand, it's an
ugly pattern to trap all exceptions when you don't have the context to decide how they
should be handled. (If Python had resumable exceptions, we could use those, but it doesn't.)
So perhaps it's cleanest to let exceptions propagate all the way up to the user --
and to design the system as much as possible for idempotency, so that if the user resolves
the problem (e.g. resolves failures of the LanguageModel call by re-establishing 
network connectivity) and resumes the discussion, they'll get sensible behaviour from subagents.
In fact, won't that happen automatically?


**Hooks.** Similar to the existing codebase, we will have hooks. However, hooks will themselves be
Agents. After all, the job of a hook is simply to process its input and return an output, which is
exactly the interface of an Agent! The difference is that by having hooks be agents, we allow them
to have internal state. 
- For example, the TodoReminder hook needs to keep track of how many queries were made since its
  last invocation. That's really internal state for the hook.

Hooks will be run at two points in the agent's core loop: they will be given either the input or the
result of the last action and invited to comment on it (just as the existing codebase has hooks
for UserPromptSubmit and PostToolUse), and they will be given a proposed action and invited to block
it (just as the existing codebase as a PreToolUse hook).

Hooks can be either dumb agents or smart agents. If the hook is implemented as a dumb agent, then
it's just a simple stateful object -- exactly like `HaveReadFilesWatcher` in the current codebase --
and the only difference is that instead of using a method 
`userpromptsubmithookoutput = HaveReadFilesWatcher.file_changed_hook(userpromptsubmithookinput)`
we now invoke the hook as
`response = file_changed_hook.response(input)`.

But by unifying the interface, we now can use smart agents as hooks. A SmartAgent hook will be easy to experiment
with, simply by rewriting its textual instructions. A language model might even decide to create
its own SmartAgent hooks!


## Actions

There are three types of action, which I'll call "primitive", "subagent", and "management".

A primitive action is like a simple API call, for example reading a file or fetching a web page, and it
is simply invoked, giving a response. Some primitive actions may be built in, such as running a bash command,
while others may be provided by MCP servers. 
- If the primitive action triggers an error, the error is wrapped up as a Result with text describing the
  nature of the error, so the LanguageModel can figure out what to do next. This is exactly as in the existing
  codebase.

A subagent action creates a new agent to perform a task. The new agent may be either dumb or smart.
Either type of agent is capable of creating its own subagents.
- The *task* action starts a new SmartAgent. Its instructions may come from a template such as an MCP resource,
  or they may be explicitly given as an argument.
- The *websearch* action starts a new dumb agent, and this dumb agent in turn launches several of its
  own smart subagents.

The design goal here is to simplify the implementation. Take *websearch* for example. In the existing codebase,
the implementation of websearch is fragmented: `websearch_impl` returns
returns `AgentCallbackPredigest` and `AgentCallback` data, which signal to the main loop in mini_agent.py
that it should launch smart subagents, and because this is done via data rather than by code there is
a rigid limitation to what can be expressed. In the new architecture, *websearch* will be an agent,
able to launch subagents directly, so all the code can be in one place. And if we decide we want richer
behaviour, we simply code it directly into the subagent: we don't need to mess around with further
elaborate datatypes that a tool might return.

In the new architecture, there is a small but significant change to how subagents behave: they will be 
persistent, and there may be several of them. The reasons for this are discussed below, under the heading "Subagents".
For now, we'll simply note that there are two extra actions that are needed for managing subagents:
- The *discuss* action is for sending information to subagents
- The *terminate* action terminates a subagent

Even though I've documented three different types of action, the LanguageModel doesn't need to care.
It simply outputs a ToolUse message. When we act on the message we look at the tool_name, and figure
out which of the actions is to be performed. In other words, from the perspective of the LanguageModel,
everything looks exactly how it does in the existing codebase.
For the implementation, we simply need a switch statement
to check whether this is a subagent or management tools, but there are very few of them, so this is not a big concern.
The existing codebase treats all actions as tools, so it doesn't need this switch statement --
but the price it pays is complex fragmented code, with callback objects and special-case handlers in mini_agent.py. 


## Subagents

In the new architecture, subagents are persistent, and there may be several of them at the same time.
Whereas in the existing codebase a subagent behaves like a primitive tool: it's invoked, it gives a result,
and then it's terminated. The new architecture is a tiny extension of what the current codebase does,
but it allows for a wide range of new behaviours:

- **More info.** Suppose we create a subagent to perform a task, but it's blocked because it needs
  clarification. It simply needs to return a result saying "I need more information". The main agent
  can then provide this extra information, and the subagent can resume. In the existing codebase,
  if a subagent needs more information then it will have to return an error, and the main agent
  will have to create a whole new subagent with more detailed instructions.

- **Memory.** The main agent can make repeated enquiries to a subagent. It's similar to having an
  aide or a personal assistant: the more they've done for us, the more accurate they're likely to be
  for the next task. One example of such an aide is a diary, or a memory bank, which we feed with information
  and can then query later on. ChatGPT is developing memory-based systems, and we can prototype
  similar systems using persistent agents.

- **Discussion.** The main agent can create several subagents, each advocating for a specific viewpoint,
  and ask them to discuss among themselves. This should be good for steel-manning an argument, or for
  making sure the agent is on very solid ground before it contradicts the user! I have seen on forums
  that many users of Claude Code open several concurrent terminals with different instances of Claude Code,
  in order to have their code looked at from different viewpoints. With the new architecture, this 
  can easily be achieved within a single Claude Code instance, and it can be automated.

All of these workflows can be achieved with just three actions: *task* to create a smart subagent,
*discuss* to share information with and between subagents, and *terminate* to end a subagent.

- *task*. The arguments for this action are {instructions, name, prompt}. The instructions
  specify the system prompt for the subagent, and may be given either as text or as a pointer
  to a file or resource. The name is how we'll refer to this subagent in future discussions.
  The prompt is optional; if it's given then the agent is asked for its response straight away.
  In this way, it can be used exactly like the `Task` tool in the existing codebase.

- *discuss*. The arguments for this action are {prompt, speakers, listeners}.
  First, the prompt is sent to all of the speakers and listeners. Then, for each speaker in turn,
  they are asked for a response. As per the interface of an agent, this response is a TextContent.
  The response is shared with all the speakers and listeners, prefixed with "[name n]" where n is
  the name of the speaker, so that they know which subagent it came from.
  The collection of all these responses is returned to the main agent
  as the result of this action. This action permits for an exchange of views between agents.

- *terminate* terminates a subagent. The argument is {name}, specifying which subagent
  to terminate.

It's interesting to observe that the communication from agents to subagents is similar to the
communication from the human user and the primary smart agent:
- The user's input is a string, provided as a TextContent prompt to the agent, in the main loop
  of user-agent interaction when we call `output = await agent.response(input)`.
  Likewise, when the agent decides to *discuss(prompt)*, the prompt will be a TextContent,
  and the subagents will be asked for their response. In both cases, the response will also
  be a TextContent.
However, what happens to responses is different:
- The main agent's response is a TextContent which is displayed to the user; then the main loop
  asks the user for input and sends it back to the agent. Whereas the subagents responses are
  all collected together by the *discuss* action, and formatted as a ToolResult object, which
  the primary agent then processes. It's done this way because all actions expect a ToolResult,
  and this signifies that the agents principal while-loop should repeat.


### Managing discussions

To make it easy for an agent to make sensible use of discussions, there will be some
sensible defaults to streamline what I think are likely to be the most common workflows.
Specifically, we'll keep track of an agent's "interlocutors", and use them as the default
speakers and listeners for the next *discuss*. These interlocutors are set when a new subagent
starts (to consist of only that subagent), and they're also set whenever *discuss* sets them explicitly.
Thus,
- If the primary agent wants to simply run a Task and the Task needs extra input,
  it can just call *discuss* and leave speakers and listeners blank,
  and the message will be sent only to the subagent running that Task.
- If the primary agent wants to set up a discussion forum and continue several rounds
  of discussion, it can again leave these fields blank.

It might be useful to have mechanisms for informing subagents in a discussion about who else
is in that discussion. This is a topic for future development. For now, let's try and keep things
simple: in the description of the *discuss* tool, we might for example instruct that a good
first discussion topic is asking everyone to introduce themselves, just like a human meeting!

Apparently it's OK to interleave different types of message, e.g. system / user / system / user.
And to have multiple user messages in a row.
Apparently we're encouraged to use system messages for background facts, project constraints, tech specs,
status updates, rules or guidelines, and to use user messages messages that expect a response. So, all 
text in the discussion should be user messages, since it's all coming from user-like entities.

There are many sorts of discussion types we might like to support, for example
a one-on-one interation with a contractor, or a meeting room discussion, or an ongoing
relationship with a consultant or aide. And surely many more! The design of the *discuss* command
is meant to be the simplest possible primitive that an agent could use to support all
of these discussion types.

The main agentic loop `response` function only ever returns text, never an error.
Even if one of the speakers has an internal error, its LanguageModel gets a chance to process the error,
and it still returns text describing what happened. This text will then be shared within the
discussion group, and returned to the calling agent. So *discuss* doesn't need to handle errors
arising generated by the speakers. The only errors it needs to deal with are the obvious ones --
badly specified arguments, etc.


### Performance implications of subagents

In the existing codebase, agents are allowed to recursively create subagents, with no limit.
In the new architecture, this is also possible -- and since the new architecture allows for multiple
persistent subagents there are new ways in which resource use could get out of hand.
There are several ways we might like to limit excessive use of subagents.

- There can be a *garbage_collecter* Hook, similar to the existing TodoReminder hook,
  which monitors to see if a subagent hasn't been spoken to for a while. It can 
  then inject a reminder to terminate that agent if it's not needed.

- There could even be a very strict Hook called *single_minded* that insists on 
  only one subagent at a time. This would prevent discussions, and ensure that one
  subagent has finished before the next is started, and thus mimic what happens
  in the existing codebase.

- If we want to limit the ability of subagents to recursively create their own
  subagents, we can have a Hook that monitors for *task* actions and blocks them
  if appropriate.

- If there's a discussion between multiple viewpoints that's been going on for a long
  time and doesn't seem to be getting anywhere, we might want it to be terminated.
  The agent who set up this discussion could be given a system prompt telling it to limit
  how much it calls *discuss*. Or this limitation could be implemented as a Hook.
  (This is where it's useful to allow Hooks to be smart agents -- it allows them to 
  make rich contextual decisions.)


## Hooks

Hooks will be implemented as Agents -- either dumb or smart -- allowing them to have complex
control structures. (It should also help to simplify the current fragmented code for hooks.)

In the existing codebase, there is a fixed set of hooks, specified as
`user_prompt_submit_hooks` in core_tools.py. There are three of them, for various system reminders --
`planning_mode`, `TodoReminder`, and `file_changed_hook`. (There's also a fourth, 
`InitialMessages.initial_hook`, but it doesn't need to be a hook since it's only used at the beginning of
the session.)

It's interesting to note that subagents are also Agents. So what's the difference between them?
The difference is that they're used for totally different purposes:
subagents are under the control of the Agent and the agent can decide how to use them,
whereas hooks are applied to the Agent and the Agent has no authority over them.
This is by design! We don't want the agent to be able to turn off its own hooks!

In the new architecture, hooks can possibly be smart Agents. This will make it very easy
to explore and prototype new hooks. Whereas in the current codebase, new hooks require coding.
Here's a use case:

- **On your toes.** We could easily create a hook that watches out for any case where the agent
  is about to disagree with the user, and pre-emptively checks that the agent has properly
  steel-manned the argument and has convincing reasons for disagreeing. This would be pretty much
  impossible to implement with classic coding, easy with a smart agent.


### Hooks for subagents

When a new subagent is created, it will be assigned all the same hooks as its parent agent.
Technically, these will be copies of the existing hooks -- now that hooks are allowed to be stateful,
we don't want subagent-hook-state to get muddled up with parent-hook-state, especially if the hook
is a smart agent with a transcript. 

This raises an interesting question about state that's meant to be shared, such as `planning_mode`.
At the moment, this is implemented as a global variable. It can of course be kept this way, for this
specific hook. For future hooks, there are several possibilities:
- Is it even desirable that a subagent should be able to exit planning mode? Maybe not!
  In that case, there might be two versions of the planning_mode hook: a read-write hook
  at the top level, and a read-only version for subagents. This is easy to implement:
  when we ask the hook to copy itself, it returns a read-only version of itself.
- If we want custom variables in global state, we could store them in the World object.
  This would function similar to stores in Svelte.

### Hook lifecycle management

In the current codebase, the hooks are installed and they persist for the entire execution.
It's interesting to explore richer lifecycles. Here are some use cases.

- **Hook expiry.** Since the agent can't control hooks (by design), who should be able to?
  One idea is that a hook itself should be able to decide when it's done. For example,
  instead of a persistent planning_mode hook with a true/false state, it could be a hook
  that's installed when we want it, and that decides to terminate itself when it sees certain
  exchanges between the user and the agent.

- **Automatic hook creation.** There could be a hook that watches out for repeated user behaviour,
  for example if the user repeatedly tells the agent not to do something, and that creates
  a custom hook for that issue. This is similar
  to how we can train a cat not to jump on counters: spray it with water whenever it does so, and it will eventually
  gain a neurosis i.e. a hook for avoiding that behaviour.

To support hook lifecycles, we can add two actions:

- *hook* action creates a new hook, with similar syntax to *task*

- *quit* action, called by the hook, causes the hook to be removed from the agent's hook list --
  and we can make it so that only hook agents have access to this action, because we have control
  over which actions each Agent has access to.


### Hooks and agency

As a future direction, it might be interesting to consider two extra actions, *meta* and *endo*,
relating to hooks and agency.
- *meta* makes the hook become primary, with the existing agent becoming subagent. (The other hooks will
  remain attached to the now-subagent.) This represents a meta-cognition moment, or an Ah-hah! moment,
  when the monitoring self steps into the spotlight. This action is available to hooks only.
- *endo(subagent)* is the opposite. The existing agent becomes a hook, and the specified subagent becomes
  the primary agent.
  
Suppose agent A is interacting with the user. Agent A may start a subagent B to look at a particular issue,
and that subagent may need user interaction. Agent A can do *endo(B)*, and now the user is talking with 
the subagent, and A is monitoring what's going on. When A decides that enough has been done, it regains
control of the session by doing *meta*.

This can enable a use-case such as Socratic teaching method. The initial agent A has an overall teaching
agenda, and it wants to create a subagent B who will engage the user in dialog. We want B to behave ignorantly,
asking the user to explain things. The monitor A will keep track of this, and subtly direct B to probe
the user in areas where the user's argument is weak.



## The World

The World is a wrapper for all the means by which an Agent can interact with things that can
be deemed to have independent existence outside itself.
(This includes getting user input, reading and writing files, and searching the web. In a larger
system it would include monitoring real-world sensors such as cameras.) The World also provides
a channel whereby actions can have an effect on the agent, for example by modifying the agent's
list of hooks or subagents.

The World object mirrors the actual phsyical world, including the filesystem. So as an object in the
architecture it's mostly stateless -- but the real physical world underneath obviously has state, and
the object mirrors this. The only parts of the World that need state are (1) connections to MCP servers,
which is part of the Env object in the current codebase, and (2) tracking of `known_content_files` 
as in core_tools in the current codebase.

It will also be possible to specify the actions that a subagent can use, as in the existing codebase. The World will
have all the tools; the Agent will have a field specifying which tools and actions are allowed. The subagent might be given 
access to all the parent agent's tools; the subagent might be given a filtered list of tools; or the subagent
template might specify additional tools that can be found on a specific MCP server.
- Example use case: if we want to prevent nested Compulsions, we can specify that a Compulsion should
  not be allowed to use the <compulsion> action, thereby preventing a situation of nested compulsions.


#### A possible race condition, and a fix

There is a potential race condition in the current codebase, which
the new architecture will also be susceptible to. It's worth documenting this now, and considering how it might be
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


## User interaction

It's simple to have /slash commands simply invoke some predefined text using a template. For example,
"/plan true" could generate the text "Start the hook for being in planning mode". Isn't that how MCP commands work -- 
they install /slash commands that simply generate some text? Possibly including system text?
Alternatively, the /slash commands could generate actions to execute straight away, bypassing the hooks
(who might otherwise disapprove of the action!)

In general, it's easy to think of special-case user commands. But I like the homoiconic design of the
system -- if a user can do it, an agent should be able to also.

It might be useful for the user to have a command to list current
hooks and subagents, and to select one of them to start talking to, i.e. to make it the primary agent.
For example, "/subagents" or "/hooks" to list them and "/talkwith [name]".
This sort of real-time introspection could be very helpful for preliminary debugging and gaining insight.
This can be done with the proposed *meta* and *endo* actions; the /slash commands are just a slightly
more user-friendly way to let the user invoke them.
- A potential issue is confusing the subagent:
  previously the messages it received were from the primary agent asking it to do things; now they'll be
  messages from the user asking it to introspect.

It'd perhaps be nice if the user could inspect the current transcripts of agents. But I note that
in Claude Code it's impossible for the user to even talk to subagents, let alone inspect their instructions,
and Claude Code is nonetheless useful! (Presumably the user
will have access to a text editor so they can easily view and edit all the stored system prompts and
agent templates; the system should make sure to use the latest versions of such files, if they've
been modified by the user in the course of an interactive session.)



## Future directions

There are several interesting ideas for extensions that can be loosely grouped under the topic of agency.

**Passing on memory.** Suppose agent A has a persistent subagent B who is concerned with some particular matter.
Suppose agent A then starts a new Task C, and thinks that C would benefit from B's experience. Maybe B could be cloned
and passed into C as C's subagent.

**Storage.** Smart agent state consists of nothing more than the current transcript, and the set of subagents
and hooks. This can all be trivially serialized. We could have user command "/dump filename" to dump the present
agent to a file, possibly remote, and a command "/restore" to bring it back. (Perhaps the natural way for /restore
would be: restore the file into a subagent, then *endo* to activate it, then what was the primary agent and 
is now a hook can *quit*.) Maybe, when an agent is restored,
it should have a system message telling it that it's just been woken up and it's in a new World. It'd also be nice
if this could be done automatically, by the agents themselves. Our general philosophy is: if the user can do X, they'll
want to be able to instruct an agent to do X.




## Rationale

### Simple implementation, complex behaviour

At its core, this new architecture is built on two primitive types, Agents and World.
The existing codebase has Hooks, and Tasks, and Env. The new architecture's Agents
subsume and generalize the existing Hooks and Tasks, and the World is mostly a cut-down version
of the existing Env, plus consolidating some floating constants.
Both the v1 and the v2 architectures need Actions by which the agents say what they want to do.

It's worth pointing out that even though the new architecture is designed to support complex agentic behaviours
and relationships, it is NOT a distributed system. The agents and subagents form a tree, not an arbitrary graph.
Communication only ever flows up and down the tree. Different subtrees are independent, so they can safely
run in parallel. A parent agent who invokes subagents will not do anything until all of its subagents have finished
their processing.

I claim that the new architecture achieves several simplifications:

- In the existing codebase, tools do not have agency, so the only way to implement a tool like *websearch*
  that needs subagents is to return a convoluted data structure, and to fragment the relevant code between the
  tool itself and the callback handlers in mini_agent.py. I'm inverting the control here and giving agency to the tools,
  which should make the code simpler. Instead of marshalling instructions into data structures then unpacking them,
  and handling them with special-cased handlers, we just use code. (It's a common observation that specification
  languages always grow into badly-designed programming languages!)

- In the existing codebase, hooks are plain functions. I'm making them be agents instead, so they'll share the
  same interface as the existing smart agents. This gives a clean way to let them have local state, which
  I believe is a more elegant architecture. It also means that the smart-agent code will automatically handle
  both subagents and hooks. This reduces the amount of special-case coding.

The new architecture describes some extra actions, in order to support new features:
- *discuss* and *terminate* for dealing with subagents
- *hook* and *quit* for managing hooks
- *meta* and *endo* for hook / subagent duality
These actions are very simple to implement!
Each agent simply has a list of hooks and agents, and these actions simply iterate or modify those lists.
It's utterly trivial code, probably no more than 20 lines at the most. And in return
we get a whole host of rich and interesting behaviour possibilities. So I think
the extra code is worth it! In fact, I think the fact that we can get all this richness with such simple code
is a sign of how well-designed the new architecture is!

Indeed, there's an elegant simplicity to these extra actions. There are two types of relationship:
from an agent UP to a hook, and from an agent DOWN to a task / subagent.
- We can add or remove in the up-direction with *hook* and *quit*
- Correspondingly we can add or remove in the down-direction with *task* and *terminate*
- To change the up-down relationship there are *meta* and *pair*
If we take as given the idea of hooks (up-relationships) and subagents (down-relationships), this set of six
actions seems to be essential, and complete. The existing codebase doesn't actually let us add or remove
hooks, but it's pretty much implied that it should be there (by the way the code has been flexibly structured),
so this set of six actions is merely rounding out what's already there.

In addition to structural actions, there is needs to be communication:
- *discuss* is for interactions with subagents, while interactions with hooks are done implicitly in the agent loop.
Again, the existing codebase supports communication for the up-direction, so the extra action *discuss* is simply
rounding out what's already there.


**Performance versus flexibility.** This new architecture is considerably more flexible than the existing codebase.
Will this lead to performance problems? There may be problems, just as the existing codebase has problems (see
the earlier discussion about resource constraints). One line of research will be to investigate different 
types of constraints that we can impose. Here are some possible directions to explore. (Remember, these are
just ideas to show that the platform is flexible enough to let us explore, they're not things we're 
actually going to build right away as part of the platform. )
- To prevent a recursive explosion of Agents, there could be a Hook that's 
  set up to watch for excessive spawning of subagents of various types, which it could then block.
- If a subagent is created and used and then left hanging around after it's no longer needed, it will
  consume memory (for its transcript) though it won't consume CPU or LanguageModel credits. It'd be easy
  to add a Hook to remind the agent to delete unnecessary subagents.
- To prevent excessive resource use by too many subagents who argue too long without getting anywhere,
  there could be a hook set up to spot the problem and tell the convening agent to close the discussion,
  deleting the subagents and freeing up resources. (This highlights the benefit of letting hooks be
  smart agents. This sort of hook would be almost impossible to implement without AI.)
- There are also plenty of hard-coded limits that it would be trivial to add should they prove necessary.
  For example, we could make it so that hook agents are not given access to the *hook* action:
  this would prevent recursive hooks. This sort of hard-coded limit is trivial to add should it
  prove necessary, so there's no point building it in the first instance into a platform designed for exploration.

**Understandability versus complexity.** This new architecture might lead to emergent behaviours that
are very hard to understand. That's a design goal for a research platform -- to design a system capable of showing rich
and sophisticated behaviour! But we'll still want to be able to review what's going on, to try to
gain understanding of the emergent properties. So of course we should support full logging of transcripts.
I expect we'll need sophisticated ways to process these logs -- we won't get very far by simply reading them.

Note that "debugging" is the classic software engineering sense is not a helpful concept here. This will be much
more like training a neural network image classifier: the code itself is straightforward (as I argued,
it has just two core primitives, Agents and World), but the behaviour
of the resulting system is complex. To "debug" what's wrong with a machine learning classifier we will
generally need statistical analysis, such as visualisation based on a dataset of many runs,
rather than traditional software-engineering style debugging. Likewise, to understand
the agentic systems I wish to explore here, it's likely that I will need to do data-science investigation of
a dataset of logs. Thus,
* For the purposes of building the platform, what matters is that it should generate full logs of transcripts,
  so that we can see exactly what happened.
* It's also useful to build some real-time introspection tools, similar to watch lists in IDEs.
  This is achieved as described under "Talking to subagents".
* For the purposes of analysis, we need our general data-science skills to make sense of these collections
  of logs. It's best practice in data science to start with exploratory analysis; it's premature to
  propose hypotheses or specific experiments until we have some understanding of the dataset.


### Rapid easy prototyping

This rewrite allows nearly all behaviours (both hooks and subagents) to be smart agents, controlled
by written text. This should make it very easy to rapidly implement complex behaviours.
In effect, we're allowing the user to write very high level code (in the form of English text), 
and using the LanguageModel as the interpreter. This should allow rapid prototyping.

It also allows for Lisp-style homoiconic development: an agent's LanguageModel can output written text
that can be used as system prompts for other hooks and agents. This opens the door to powerful
manipulations -- though (like Lisp) it's almost impossible to imagine in advance the richness of
what can be created.

At the same time, we allow hooks and subagents to be just plain dumb agents, as they are
in the existing codebase. This can be helpful to give us a more stable base for exploration and
research.

In Smalltalk's live-coding environment, the user is able to inspect and modify code on the fly.
I imagine that the user might be using a standalone IDE to inspect and edit the templates that are
stored in the filesystem -- the templates that are used when creating new agents. It'd also be
nice to have a live environment that lets users easily explore the actual live system prompts
and transcripts. That's something to explore further.
