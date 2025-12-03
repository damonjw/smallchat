import json
import collections
import inspect
import litellm
from utils import function_to_tool, spinner, as_described, try_repeatedly
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
        self.world = World([self.task, self.discuss])
        self.session = session
        self.subagents = {}
        self.transcript = transcript if transcript is not None else []

    def harken(self, input):
        role,content = (input['role'],input['content']) if isinstance(input,dict) else ('user',input)
        assert isinstance(content, (str, TrackedString, StringWithCause)), "Expected a string input"
        m = {'role':role, 'content':str(content)}
        self.transcript.append(m)
        substance = content.message_id if isinstance(content, TrackedString) else None
        cause = content.cause if isinstance(content, StringWithCause) else None
        self.session.log_transcript_entry(**m, agent=self, substance=substance, cause=cause)

    async def response(self, input=None):
        if input is not None: self.harken(input)
        # TODO: check if the LLM can accept a transcript that doesn't end in a 'user' message.
        # Can it end in a system message? Can I put in an empty user message?
        assert len(self.transcript) > 0 and self.transcript[-1]['role'] == 'user'
        while True:
            res = await try_repeatedly(lambda: spinner(litellm.acompletion(model=self.language_model, messages=self.transcript, tools=self.world.tools)))
            res = res.choices[0].message
            self.transcript.append(res)
            tool_calls = [t.model_dump() for t in res.tool_calls] if res.tool_calls else None # sanitized json-able version
            msg_id = self.session.log_transcript_entry(role=res.role, content=res.content, tool_calls=tool_calls, agent=self)
            if not res.tool_calls:
                return TrackedString(res.content, message_id=msg_id)
            else:
                for t in res.tool_calls:
                    cause = f"{msg_id}.{t.id}"
                    self._current_tool_call = cause
                    res = await self.world.do_action(t)
                    del self._current_tool_call
                    m = {'role':'tool', 'tool_call_id':t.id, 'name':t.function.name, 'content':str(res)}
                    self.transcript.append(m)
                    self.session.log_tool_use(**m,
                                              agent = self,
                                              tool_call = msg_id,
                                              substance = res.message_id if isinstance(res,TrackedString) else None,
                                              cause = res.cause if isinstance(res,StringWithCause) else None)


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
        self.session.log_agent_created(agent=a, name=name, cause=self._current_tool_call, parent=self)
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
