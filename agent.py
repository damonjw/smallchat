import json
import collections
import inspect
import litellm
from utils import function_to_tool, spinner, as_described, try_repeatedly
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
        # TODO: catch errors, and return them as content
        f = self.f[t.function.name]
        args = json.loads(t.function.arguments)
        res = await f(**args) if inspect.iscoroutinefunction(f) else f(**args)
        return res




class Agent:
    def __init__(self, init_prompt=None):
        self.language_model = 'anthropic/claude-sonnet-4-5-20250929'
        if init_prompt is None: init_prompt = []
        self.transcript = init_prompt if isinstance(init_prompt, list) else [init_prompt]
        self.world = World([self.task, self.discuss])
        self.subagents = {}

    def inform(self, input):
        assert isinstance(input, str), "Expected a string input"
        self.transcript.append({'role':'user', 'content':input})

    async def response(self, input=None):
        if input is None:
            assert len(self.transcript) > 0 and self.transcript[-1]['role'] == 'user'
        else:
            assert isinstance(input, str), "Expected a string input"
            self.transcript.append({'role':'user', 'content':input})
        while True:
            res = await try_repeatedly(spinner(litellm.acompletion(model=self.language_model, messages=self.transcript, tools=self.world.tools)))
            res = res.choices[0].message
            self.transcript.append(res)
            if not res.tool_calls:
                return res.content
            else:
                for t in res.tool_calls:
                    result = await self.world.do_action(t)
                    m = {'role':'tool', 'tool_call_id':t.id, 'name':t.function.name, 'content':result}
                    self.transcript.append(m)


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
        self.subagents[name] = Agent(init_prompt={'role':'system', 'content':system_prompt})
        print(f'<Task name="{name}" user_prompt={"..." if user_prompt else None}/>')
        if user_prompt:
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
            print("->", prompt)
            for s in self.speakers + self.listeners:
                self.subagents[s].inform(prompt)
        # A round of discussion
        if len(self.speakers) == 1 and len(self.listeners) == 0:
            a = self.subagents[self.speakers[0]]
            res = await a.response()
            print("<-", res)
            return res
        else:
            res = []
            for s in self.speakers:
                a = self.subagents[s]
                resp = await a.response()
                msg = f"[{s}]: {resp}"
                print("<-", msg)
                for t in self.speakers + self.listeners:
                    if t == s: continue
                    self.subagents[t].inform(msg)
                res.append(msg)
            return '\n\n'.join(res)


        



async def main():
    import readline # so that `input` lets me use cursor keys
    a = Agent()
    while True:
        prompt = input("> ")
        response = await a.response(prompt)
        print(response)

"""
Create a subagent, and tell it to find the time of sunset in Cambridge today, then report the answer back to me.
"""

if __name__ == '__main__':
    import dotenv
    import asyncio
    dotenv.load_dotenv() # loads ANTHROPIC_API_KEY into environment variables
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, EOFError):
        print()

