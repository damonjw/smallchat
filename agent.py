import json
import collections
import inspect
from utils import function_to_tool, as_described, completion
from session import TrackedString, StringWithCause, Session
import prompts


EXTERNAL_TOOLS = [
    {'name': "web_search", 'type': "web_search_20250305", 'max_uses': 5}
]


class World:
    def __init__(self, tools):
        """Sets up self.tools (a list suitable for giving to LLM) and self.f (a dictionary of name:function)"""
        n = collections.defaultdict(int)
        self.f = {}
        for f in tools:
            i = n[f.__name__]
            self.f[f.__name__+(str(i) if i > 0 else '')] = f
            n[f.__name__] = i + 1
        self.tools = EXTERNAL_TOOLS + [function_to_tool(f,name=n) for n,f in self.f.items()]

    def with_tools(self, extra_tools):
        got_tools = list(self.f.values())
        return World(got_tools + [t for t in extra_tools if t not in got_tools])

    async def do_action(self, t):
        """Perform an action and return a string result.

        If the result is basically the same substance as some previously-logged string, return it as TrackedString.
        If the result is the causal outcome of processing several previously-logged strings, return it as a StringWithCause.
        """
        # TODO: catch errors, and return them as content
        f = self.f[t.function.name]
        args = json.loads(t.function.arguments)
        res = await f(**args) if inspect.iscoroutinefunction(f) else f(**args)
        return res



class Agent:
    def __init__(self, language_model, session, transcript=None):
        self.language_model = language_model
        self.transcript = []
        self.world = World([self.task, self.discuss, self.hook])
        self.session = session
        self.subagents = {}
        self.transcript = transcript if transcript is not None else []
        self.hooks = [] # In the future, there'll be tools to add hooks

    def harken(self, input):
        role,content,extra = (input['role'],input['content'],input) if isinstance(input,dict) else ('user',input,{})
        assert isinstance(content, (str, TrackedString, StringWithCause)), "Expected a string input"
        m = extra | {'role':role, 'content':str(content)}
        self.transcript.append(m)
        substance = content.message_id if isinstance(content, TrackedString) else None
        cause = content.cause if isinstance(content, StringWithCause) else None
        self.session.log_transcript_entry(**m, agent=self, substance=substance, cause=cause)

    async def response(self, input=None):
        if input is not None: self.harken(input)
        assert any(m for m in self.transcript if m['role'] != 'system'), "Need at least one non-system message to respond to"
        while True:
            res = await completion(model=self.language_model, messages=self.transcript, tools=self.world.tools)
            self.transcript.append(res)
            tool_calls = [t.model_dump() for t in res.tool_calls] if res.tool_calls else None # sanitized json-able version
            msg_id = self.session.log_transcript_entry(role=res.role, content=res.content, tool_calls=tool_calls, agent=self)
            # Call all the tool_calls, put their result in the transcript, then continue and see what the LLM says to do next.
            # I'm setting self._current_tool_call so that my internal tools can log the cause.
            # It'd be cleaner to call world.do_action(t,current_tool_call), but then the tools would have to accept
            # an extra argument, and I don't like adding arguments purely for logging purposes.
            if res.tool_calls:
                for t in res.tool_calls:
                    self._current_tool_call = f"{msg_id}.{t.id}"
                    #try:
                    res = await self.world.do_action(t)
                    m = {'role':'tool', 'tool_call_id':t.id, 'name':t.function.name, 'content':str(res)}
                    #except Exception as e:
                    #    m = {'role':'tool', 'tool_call_id':t.id, 'name':t.function.name, 'content':str(e), 'is_error':True}
                    del self._current_tool_call
                    self.transcript.append(m)
                    self.session.log_tool_use(**m,
                                              agent = self,
                                              tool_call = msg_id,
                                              substance = res.message_id if isinstance(res,TrackedString) else None,
                                              cause = res.cause if isinstance(res,StringWithCause) else None)
                continue # repeat the agentic loop
            # Run the response (res.content, just added to the transcript) past all my hooks.
            # If any hook has a problem, note it down as a user message, then try again
            problem = None
            for h in self.hooks:
                problem = await h.comment_on_last_response()
                if problem is not None:
                    self.harken(f"<system>{problem}</system>")
                    break
            if problem is not None:
                continue # repeat the agentic loop
            # We've come to the end of agentic processing. Return the result to the user.
            return TrackedString(res.content, message_id=msg_id)


    def recall(self, n):
        # Read a prompt / response from the transcript.
        # TODO: this will evolve, as I figure out what sort of transcript-reading is useful
        request_index = [i for i,m in enumerate(self.transcript) if m['role'] == 'user' and not m['content'].startswith('<system>')]
        if n<0: n = len(request_index) + n
        i = request_index[n]
        req = self.transcript[i]
        inext = request_index[n+1] if n+1<len(request_index) else len(self.transcript)
        resp = {}        
        for j in range(inext-1, i, -1):
            msg = self.transcript[j]
            if msg['role'] == 'assistant' and not msg.get('tool_calls',None):
                resp = msg
                break
        return {'request': req.get('content',None), 'response': resp.get('content',None), 'n': n}


    @as_described(prompts.HOOK)
    async def hook(self, instructions):
        """
        Args:
          instructions (string): the prompt to be used by the hook whenever it evaluates an utterance
        """
        # TODO: would any extra logging of string provenance be useful?
        print(f"<Hook {len(self.hooks)+1}>")
        a = Agent(language_model=self.language_model, session=self.session)
        h = SmartHook(monitored_agent=self, internal_agent=a, prompt=instructions)
        self.session.log_agent_created(agent=a, name='hook_', parent=self, cause=self._current_tool_call, role='hook')
        self.hooks.append(h)
        # Give it a system prompt
        system_prompt = SmartHook.SYSTEM
        a.harken({'role':'system', 'content':system_prompt})


    @as_described(prompts.TASK)
    async def task(self, name, system_prompt, user_prompt=None):
        """
        Args:
          name (string): the name of the new subagent
          system_prompt (string): the instructions to be given to the new subagent as a system prompt
          user_prompt (string): a query to be sent to the subagent for immediate response
        """
        if name in self.subagents:
            raise ValueError("There is already a subagent of this name")
        print(f'<Task name="{name}" user_prompt={"..." if user_prompt else None}/>')
        a = Agent(language_model=self.language_model, session=self.session)
        self.subagents[name] = a
        self.session.log_agent_created(agent=a, name=name, parent=self, cause=self._current_tool_call, role='child')
        # Give it the system and user prompt
        system_prompt = {'role':'system', 'content': StringWithCause(system_prompt,cause=[self._current_tool_call])}
        a.harken(system_prompt)
        if user_prompt:
            user_prompt = self.session.logged_fragment(agent=self, content=user_prompt, cause=self._current_tool_call)
            res = await self.subagents[name].response(user_prompt)
            return res
        else:
            return json.dumps({'subagents': list(self.subagents.keys()), 'status': f"Created subagent: {name}"})


    @as_described(prompts.DISCUSS)
    async def discuss(self, prompt=None, speakers=None, listeners=None):
        """
        Args:
          prompt (string): the starting point for the discussion, which is shared between all the participants
          speakers (list[string]): names of the subagents who will contribute to the discussion
          listeners (list[string]): names of the subagents who will listen to the discussion but not contribute
        """
        # Tedious book-keeping to make sure the list of speakers and listeners is sensible
        if hasattr(self, 'speakers'):
            self.speakers = [s for s in self.speakers if s in self.subagents]
        else:
            self.speakers = list(self.subagents.keys())
        if speakers is not None:
            for s in speakers:
                if s not in self.subagents.keys():
                    raise KeyError(f"No subagent has name: {s}")
            self.speakers = speakers
        if len(self.speakers) == 0:
            subagent_list = list(self.subagents.keys())
            if len(subagent_list) == 0:
                raise KeyError("No subagents available. Use the Task tool to create a subagent.")
            avail = ', '.join([f'"{n}"' for n in subagent_list])                        
            raise ValueError(f"No speakers specified. Available speakers: [{avail}]")
        if hasattr(self, 'listeners'):
            self.listeners = [s for s in self.listeners if s in self.subagents.keys()]
        else:
            self.listeners = []
        if listeners is not None:
            for s in listeners:
                if s not in self.subagents.keys():
                    raise KeyError(f"No subagent has name: {s}")
            self.listeners = [s for s in listeners if s not in self.speakers]
        # Send the prompt out
        if prompt is not None:
            prompt = self.session.logged_fragment(agent=self, content=prompt, cause=self._current_tool_call)
            print("->", prompt)
            for s in self.speakers + self.listeners:
                self.subagents[s].harken(prompt)
        # A round of discussion
        if len(self.speakers) == 1 and len(self.listeners) == 0: # TODO: in this case, no need for the fragment: the substance is just the tool call
            a = self.subagents[self.speakers[0]]
            res = await a.response()
            print("<-", res)
            return StringWithCause(str(res), cause=[res.message_id])
        else:
            res = []
            for s in self.speakers:
                a = self.subagents[s]
                resp = await a.response()
                msg = TrackedString(f"[{s}]: {resp}", message_id=resp.message_id)
                print("<-", msg)
                for t in self.speakers + self.listeners:
                    if t == s: continue
                    self.subagents[t].harken(msg)
                res.append(msg)
            return StringWithCause('\n\n'.join(str(r) for r in res), cause=[r.message_id for r in res])



class SmartHook:
    SYSTEM = """Your job is to evaluate the most recent request/response pair in a log, and to check 
if the response is acceptable. The requirements for a response to be acceptable are provided below.
- If the response is acceptable, simply respond OK.
- If the response is unacceptable, use the reject tool to mark it as unacceptable.
"""


    def __init__(self, monitored_agent, internal_agent, prompt):
        self.monitored_agent = monitored_agent
        self.internal_agent = internal_agent
        self.internal_agent.world = self.internal_agent.world.with_tools([self.reject, self.read_log])
        self.prompt = prompt
        self._transcript_additions = []

    async def comment_on_last_response(self):
        # I'll let the internal agent use its transcript for working, then at the end of this call I'll reset it
        # to the length it is now (except for anything it explicitly decides it needs to remember).
        # TODO: it'd make more sense to have this transcript-session grow until the response is finally approved.
        _original_transcript_length = len(self.internal_agent.transcript)
        self._denied = None
        # Instruct the internal agent to evaluate the monitored_agent's last response, and give it the preliminary data it needs.
        self.internal_agent.harken(self.prompt)
        self.internal_agent.harken({'role': 'assistant', 
                                    'content': "Reading the last request/response pair",
                                    'tool_calls': [{'id':'ephemeral1', 'type':'function', 'function':{'name':'read_log', 'arguments':'{"n": -1}'}}]})
        self.internal_agent.harken({'role': 'tool',
                                    'content': self.read_log(-1),
                                    'tool_call_id': 'ephemeral1',
                                    'name': 'read_log'})
        res = await self.internal_agent.response()
        # Wipe this conversation from the internal_agent's memory
        self.internal_agent.transcript = self.internal_agent.transcript[:_original_transcript_length]
        # Return an error message, or None if it's OK
        return self._denied

    @as_described("Use this tool to mark a response as unacceptable.")
    def reject(self, reason):
        """
        Args:
          reason (str): The reason why this response is unacceptable, and a reminder of what is acceptable
        """
        self._denied = reason
        return "response status: denied"

    @as_described("This tool reads a request/response pair from the log.")
    def read_log(self, n):
        """
        Args:
          n (int): Which log item to read. Use standard Python indexing, e.g. n=-1 gets the most recent log item, n=0 gets the first.
        """
        return json.dumps(self.monitored_agent.recall(n))

        