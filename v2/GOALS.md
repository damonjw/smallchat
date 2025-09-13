# Goals of new architecture

The goal is to build a research platform for exploring complex agentic behaviours.
- Note that the existing codebase is also just a research demo, and it has no users.
  So there is no concern about migration.

The main goal is to explore the space of designs for new complex agentic behaviours. 
We know that agentic behaviours can do great things: Claude Code is proof that just
a little bit of cleverness (hooks and Tasks) is enough to make a fantastically useful assistant.
This redesigned architecture is intended as a platform for exploring what can be achieved
with further mechanisms.

I am primarily interested in ways to create agentic systems to do things that
are useful to the user. I don't want there to be things that can only be achieved by
special instruction from the user, or by modifying the codebase: I want a system
where agents themselves can do these things themselves, on behalf of the user.


## General design principles for research platforms

A good design for a research platform is that it should have just a few primitives that are simple to *implement*,
and which allow for very complex and sophisticated *emergent behaviour*. Think of neural networks, where
some very simple linear algebra leads to amazing results.

A good design for a research platform allows for rapid prototyping. It should be very easy to
inspect and modify how things work. A wonderful example is Smalltalk-style live coding environment.

This platform is meant to be general enough
to help us explore what sort of agent behaviours would be useful in other scenarios,
going far beyond code assistants. For example, teaching, literature review, study, brainstorming,
essay writing, creative writing.


## Use cases

Here are some first thoughts about new types of agentic behaviour that it'd be interesting to explore.
Hopefully, the new architecture should make it easy to build them.

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
  can simply tell the agent to create a smart-agent Hook that monitors subagent creation, and blocks it when 
  appropriate. It's much simpler that writing our own hooks with code: it's easy to be expressive because it has
  the full power of a language model behind it.

- **Steel man reasoning.**
  We could for example create a Hook that reminds the agent: "if you're disagreeing with the user,
  then set up a subagent advocating for the user's point of view so that you can make sure your points
  aren't easily rebutted." This would make for a better experience for precise-minded users, like myself.
  It would be very fiddly to achieve this in the current system of hooks and tasks, but it'd be trivial
  to achieve this in the redesign, just by giving textual expression.

- **Long-term memory.** ChatGPT is exploring various ways of creating long-term "memory" of the user.
  For example, we might like to feel that we're coming back to a trusted collaborator who knows how we think.
  In other words, there are agents who become more valuable the longer we interact with them.
  Could this be build out of a smart-agent hook (that monitors user interactions) combined with 
  long-term storage?

- **Multiple characters.** Consider an agent that's helping with writing a story, or that's reviewing a
  story. We could spin up subagents for each of the characters, feed them only what they perceive, and
  then ask if the actions in the story are true to their natures. Or there could be a hook that looks
  out for world-building inconsistencies, or that goes off to do research to verify facts.

- **Event-driven agents.** What if an agent could be receptive to truly asynchronous triggers? For example,
  we could have a trigger that notifies an agent when the stock market hits a certain level. Or an agent
  could invoke a "lazy" tool, like running a slow command, and the agent could be notified when that
  tool finishes -- so the agent can carry on and be responsive to the user, and also act on the new data
  when it arrives.

- **Socratic teaching.** In Socratic teaching, the teacher asks questions "disingenuously": the teacher knows
  where the answers need to go, and pretends to be asking naive questions. It seems hard to achieve this
  split personality within a single agent. It's likely that we'd need some sort of multi-agent system,
  in which one agent guides the other.
  
- **Stategic thinking.** To generalize the Socratic teaching example: there are surely many situations where
  we want to nudge short-term tactical thinking to match long-term strategic thinking. In Claude Code, the
  TodoWrite and TodoReminder kind of achieve this -- but they don't allow for very much strategic thinking
  beyond just a bullet list of todo items. Perhaps an agent / subagent design would be better?

