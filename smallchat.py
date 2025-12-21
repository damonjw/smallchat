import asyncio
import readline  # so that `input` lets me use cursor keys
from pathlib import Path
import argparse
import dotenv
import os
import sys
import webbrowser
import time
import litellm
from agent import Agent, SmartHook
from session import Session
from server import start_server
import tempfile
import atexit

dotenv.load_dotenv() # loads ANTHROPIC_API_KEY into environment variables
SESSIONS_DIR = Path('.chats')
FILENAME_PATTERN = 'chat{}.jsonl'

parser = argparse.ArgumentParser()
session_group = parser.add_mutually_exclusive_group()
session_group.add_argument('--new', action='store_true', help="Start a new chat session")
session_group.add_argument('--resume', type=str, metavar='FILENAME', help="Resume existing chat session")
session_group.add_argument('--temp', action='store_true', help="Start a new temporary (unlogged, unresumable) chat session")
parser.add_argument('-nw', '--no-window', action='store_true', help="Don't open browser window")
parser.add_argument('--model', type=str, default='anthropic/claude-sonnet-4-5-20250929',
                    help="Language model to use for new sessions (default: anthropic/claude-sonnet-4-5-20250929)")
parser.add_argument('--list-models', action='store_true', help="List available models")

def list_models():
    keys = ['OPENAI_API_KEY', 'GEMINI_API_KEY', 'XAI_API_KEY', 'ANTHROPIC_API_KEY']
    print(f"Model use requires an API access key in .env or as an environment variable")
    print(f"- Providers with keys: {', '.join(k for k in keys if k in os.environ)}")
    print(f"- Providers without keys: {', '.join(k for k in keys if k not in os.environ)}")
    print("Available models:")
    for m in litellm.get_valid_models(check_provider_endpoint=True):
        print("- ",m)
    print("Use the `--model M` option to specify the model for the primary agent")

def get_session(args):
    # What do we want to do: resume session, or new session?
    if args.resume:
        action,filename = ('resume', args.resume)
    elif args.new:
        action,filename = ('new', 'AUTO')
    elif args.temp:
        action,filename = ('new', None)
    else: # resume most recent
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        filenames = list(SESSIONS_DIR.glob('*.jsonl'))
        if filenames:
            most_recent = max(filenames, key = lambda p: p.stat().st_mtime)
            action,filename = ('resume', most_recent)
        else:
            action,filename = ('new', 'AUTO')
    if action == 'new':
        if not filename:
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
                filename = f.name
            atexit.register(lambda: os.unlink(filename) if os.path.exists(filename) else None)
        else:
            i = 0
            while True:
                fn = SESSIONS_DIR / Path(FILENAME_PATTERN.format(i))
                i = i + 1
                if not fn.exists(): break
            filename = fn
    # Do it!
    if action == 'new':
        print(f"Logging to {filename}")
        print(f"Using language model: {args.model}")
        session = Session(str(filename))
        a = Agent(session=session, language_model=args.model)
        session.log_agent_created(a, cause='user', parent='user', name='Primary', role='primary')
    else:
        print(f"Resuming from {filename}")
        def construct_agent(session, language_model, transcript): 
            return Agent(session=session, language_model=language_model, transcript=transcript)
        def construct_hook(monitored_agent, internal_agent):
            return SmartHook(monitored_agent=monitored_agent, internal_agent=internal_agent, prompt=None)
        session = Session.load(str(filename), construct_agent, construct_hook)
    return session


async def interact(session):
    while True:
        prompt = input("> ")
        prompt = session.logged_fragment(agent='user', cause='user', content=prompt)
        response = await session.interlocutor.response(prompt)
        print(response)


"""
Create a subagent, and tell it to find the time of sunset in Cambridge today, then report the answer back to me.
"""

if __name__ == '__main__':
    args = parser.parse_args()
    if args.list_models:
        list_models()
        sys.exit(0)
    session = get_session(args)

    if not args.no_window:
        SERVER_PORT = 5000
        print(f"Starting web viewer at http://127.0.0.1:{SERVER_PORT}")
        start_server(session._log_filename, port=SERVER_PORT)
        time.sleep(0.5)
        webbrowser.open(f'http://127.0.0.1:{SERVER_PORT}')

    try:
        asyncio.run(interact(session))
    except (KeyboardInterrupt, EOFError):
        print()
