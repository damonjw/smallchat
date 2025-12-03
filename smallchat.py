import asyncio
import readline  # so that `input` lets me use cursor keys
from pathlib import Path
import argparse
import dotenv
import webbrowser
import time
from agent import Agent
from session import Session
from server import start_server

dotenv.load_dotenv() # loads ANTHROPIC_API_KEY into environment variables
SESSIONS_DIR = Path('.chats')
FILENAME_PATTERN = 'chat{}.jsonl'

parser = argparse.ArgumentParser()
session_group = parser.add_mutually_exclusive_group()
session_group.add_argument('--new', action='store_true', help="Start a new chat session")
session_group.add_argument('--resume', type=str, metavar='FILENAME', help="Resume existing chat session")


def get_session(args):
    # What do we want to do: resume session, or new session?
    if args.resume:
        action,filename = ('resume', args.resume)
    elif args.new:
        action,filename = ('new', None)
    else:
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        filenames = list(SESSIONS_DIR.glob('*.jsonl'))
        if filenames:
            most_recent = max(filenames, key = lambda p: p.stat().st_mtime)
            action,filename = ('resume', most_recent)
        else:
            action,filename = ('new', None)
    if action == 'new':
        i = 0
        while True:
            fn = SESSIONS_DIR / Path(FILENAME_PATTERN.format(i))
            i = i + 1
            if not fn.exists(): break
        filename = fn
    # Do it!
    if action == 'new':
        print(f"Logging to {filename}")
        session = Session(str(filename))
        a = Agent(session=session, language_model='anthropic/claude-sonnet-4-5-20250929')
        session.log_agent_created(a, cause='user', parent='user', name='Primary')
    else:
        print(f"Resuming from {filename}")
        def construct_agent(session, language_model, transcript): 
            return Agent(session=session, language_model=language_model, init_prompt=transcript)
        session = Session.load(str(filename), construct_agent)
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
    session = get_session(args)

    # Start the Flask server with SSE for live viewer updates
    SERVER_PORT = 5000
    print(f"Starting web viewer at http://127.0.0.1:{SERVER_PORT}")
    start_server(session._log_filename, port=SERVER_PORT)

    # Give the server a moment to start, then open the browser
    time.sleep(0.5)
    webbrowser.open(f'http://127.0.0.1:{SERVER_PORT}')

    try:
        asyncio.run(interact(session))
    except (KeyboardInterrupt, EOFError):
        print()
