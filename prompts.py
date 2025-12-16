TASK = """
This tool creates a subagent for handling ambiguous, complex or multi-step tasks.

Subagents are persistent. They are more like personal assistants than like subroutines.
There are several ways to use them:

1. If you leave the user_prompt blank, the agent will await further instructions via the Discuss
tool. This is appropriate if you plan to repeatedly prompt the agent and get back its responses.

2. If you plan to create several subagents and have them collectively take part
in a discussion, you can leave also user_prompt blank. It's a good idea to specify in the system_prompt that the subagent will be
a participant in a discussion, and that anything the other participants say will appear as 
a user message prefixed by "[name n]: msg".

3. If you specify the user_prompt, you'll get back an immediate response. This is appropriate if you
want a one-off answer to a complex query. Note though that the subagent might reply asking for clarification,
in which case you will have to continue instructing it using the Discuss tool.
The user will have no knowledge of how the sub-agent responded, and they cannot read its
final report. Anything you want the user to know, you must report to the user yourself.
Once you have no more need of the subagent, use the Terminate tool to end it.

You must take care to give the sub-agent a good system_prompt. The sub-agent knows nothing of your
context. You must put into the system_prompt everything that the sub-agent needs to know 
about how it is to behave. Also, when you create a subagent, give it a catchy name --
for example, for a subagent who is tasked with searching the web, the name "Wendell Websearcher" is more interesting
than "web_searcher".

"""

HOOK = """
This tool creates a hook, which can be used to enforce policies that the user has asked you to adhere to. 

The hook will will monitor everything that you say, and if necessary issue reminders or corrections.
If the hook decides that what you said is acceptable, what you say will be conveyed back to the user.
If not, it will tell you why it's not acceptable.
"""

HOOK_SYSTEM = """
Your job is to evaluate the most recent request/response pair in a log, to ensure that the response adheres to policy.
The policy will be provided below. If the response adheres to policy, then output the single word ok.
Otherwise, explain why the response does not adhere to policy. Use the read_log tool to read from the log.
"""

MEMO = """
This tool is for making a note to yourself.
"""

READ_LOG = """
This tool reads a request/response pair from the log.
"""


DISCUSS = """
This tool chairs a round of discussion among subagents. The subagents should previously 
have been created using the Task tool.

First, the prompt is sent to all of the speakers and listeners. Then, for each speaker in turn,
they are asked for a response. The response is shared with all the speakers and listeners, 
prefixed with "[name n]" where n is the name of the speaker, so that they know which subagent it came from.

To simply continue the next round of discussion, set prompt=None (the default). Each speaker
will, since it last spoke, have heard from the other speakers. So it should have something
relevant to say, even without a prompt from the chair.
To use the same speakers and listeners as in the last call to this tool, leave speakers=None and listeners=None
(the default). If this is the first use of this tool, then speakers=None means all subagents, and listeners=None
means no listeners.

**Example usage:**
1. For the first use of this tool, the prompt might inform all the participants that they are 
in a discussion, telling them who else is participating, and reminding them that anything the other
participants say will appear as user messages prefixed by "[name n]: msg". It might also ask
the participants to introduce themselves, just like in a human meeting.
Use speakers=None and listeners=None to make all subagents be participants.
2. The second use of this tool might specify a prompt giving the topic for discussion, for example 
proposing a task or asking a question, and asking the speakers to discuss it amongst themselves.
3. Subsequent uses of this tool might have prompt=None so that the discussion simply continues.

**Example usage:**
The tool can also be used for a back-and-forth with a single subagent.
In this case, the first use of the tool will specify speaker=[name of subagent] and listeners=None,
and give a prompt. Each subsequent use will also specify a prompt, but leave speaker=None and listeners=None.

The result of this tool is a list of all of the responses from each of the speakers, 
each in the form "[name n]: response". Unless there is only one speaker, in which case the
result is just a string with that speaker's response.

You will have no insight into how the subagent come up with their responses. You will only see
the subagent's response to this round of the discussion. You should put into the prompt any
instructions you want to give about what that response should include.
"""

