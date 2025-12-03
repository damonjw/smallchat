"""
Flask HTTP server with Server-Sent Events (SSE) for live session streaming.

This module provides a web interface to the smallchat agent platform:
- Serves the viewer static files
- Streams session log updates via SSE
- Watches the session file and pushes new events to connected clients
"""

import os
import time
import json
import logging
from pathlib import Path
from flask import Flask, send_from_directory, Response
from threading import Thread, Lock
import queue

# Suppress werkzeug logging output (startup messages and HTTP requests)
import sys
import werkzeug.serving
import werkzeug._internal
import click

# Patch werkzeug's internal logging functions
werkzeug.serving._log = lambda *args, **kwargs: None
werkzeug._internal._log = lambda *args, **kwargs: None

# Also patch click.echo which werkzeug uses for startup messages
_original_click_echo = click.echo
def _silent_click_echo(message=None, **kwargs):
    # Suppress messages that start with ' * ' (werkzeug startup messages)
    if message and isinstance(message, str) and message.strip().startswith('*'):
        return
    _original_click_echo(message, **kwargs)
click.echo = _silent_click_echo

app = Flask(__name__)

# Global state for the current session
current_session_file = None
current_session_lock = Lock()
event_queues = []  # List of queues for connected SSE clients
event_queues_lock = Lock()


def set_session_file(filepath):
    """Set the current session file to watch."""
    global current_session_file
    with current_session_lock:
        current_session_file = filepath


def broadcast_event(event_data):
    """Broadcast an event to all connected SSE clients."""
    with event_queues_lock:
        for q in event_queues:
            try:
                q.put(event_data, block=False)
            except queue.Full:
                pass  # Skip if queue is full


def watch_session_file():
    """Background thread that watches the session file for new events."""
    last_position = 0
    last_mtime = 0

    while True:
        time.sleep(0.1)  # Check every 100ms

        with current_session_lock:
            filepath = current_session_file

        if not filepath or not os.path.exists(filepath):
            continue

        try:
            mtime = os.path.getmtime(filepath)

            # Only read if file has been modified
            if mtime > last_mtime:
                last_mtime = mtime

                with open(filepath, 'r') as f:
                    f.seek(last_position)
                    new_content = f.read()
                    last_position = f.tell()

                # Parse and broadcast new events
                if new_content.strip():
                    for line in new_content.strip().split('\n'):
                        line = line.strip()
                        if line:  # Skip blank lines
                            try:
                                event = json.loads(line)
                                broadcast_event(event)
                            except json.JSONDecodeError:
                                pass  # Skip invalid JSON

        except Exception as e:
            # Continue watching even if there's an error
            pass


@app.route('/')
def index():
    """Serve the viewer index.html."""
    viewer_dist = Path(__file__).parent / 'viewer' / 'dist'
    return send_from_directory(viewer_dist, 'index.html')


@app.route('/<path:path>')
def static_files(path):
    """Serve static files from viewer/dist/."""
    viewer_dist = Path(__file__).parent / 'viewer' / 'dist'
    return send_from_directory(viewer_dist, path)


@app.route('/session-info')
def session_info():
    """Return information about the current session."""
    with current_session_lock:
        filepath = current_session_file

    if filepath:
        filename = os.path.basename(filepath)
        return {'filename': filename}
    return {'filename': 'Session'}


@app.route('/events')
def events():
    """SSE endpoint that streams session log events."""
    def event_stream():
        # Create a queue for this client
        q = queue.Queue(maxsize=100)

        with event_queues_lock:
            event_queues.append(q)

        try:
            # First, send all existing events from the current session file
            with current_session_lock:
                filepath = current_session_file

            if filepath and os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line:  # Skip blank lines
                            try:
                                event = json.loads(line)
                                yield f"data: {json.dumps(event)}\n\n"
                            except json.JSONDecodeError:
                                pass

            # Then stream new events as they arrive
            while True:
                try:
                    event = q.get(timeout=30)  # 30-second timeout for keep-alive
                    yield f"data: {json.dumps(event)}\n\n"
                except queue.Empty:
                    # Send keep-alive comment
                    yield ": keep-alive\n\n"

        finally:
            # Clean up when client disconnects
            with event_queues_lock:
                if q in event_queues:
                    event_queues.remove(q)

    return Response(event_stream(), mimetype='text/event-stream')


def run_server(host='127.0.0.1', port=5000):
    """Run the Flask server in the current thread."""
    app.run(host=host, port=port, debug=False, threaded=True, use_reloader=False)


def start_server(session_file, host='127.0.0.1', port=5000):
    """
    Start the Flask server in a background thread.

    Args:
        session_file: Path to the session JSONL file to watch
        host: Host to bind to (default: 127.0.0.1)
        port: Port to listen on (default: 5000)

    Returns:
        tuple: (server_thread, watcher_thread) - both daemon threads
    """
    # Suppress Flask and werkzeug logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.logger.setLevel(logging.ERROR)

    set_session_file(session_file)

    # Start the file watcher thread
    watcher_thread = Thread(target=watch_session_file, daemon=True)
    watcher_thread.start()

    # Start the Flask server thread
    server_thread = Thread(target=run_server, args=(host, port), daemon=True)
    server_thread.start()

    return server_thread, watcher_thread
