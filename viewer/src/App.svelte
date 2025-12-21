<script>
  import { onMount } from 'svelte';
  import { agents, allMessages, logData, panels } from './stores.js';
  import { parseLog, processEvent } from './logParser.js';
  import AgentHierarchy from './AgentHierarchy.svelte';
  import ChatPanels from './ChatPanels.svelte';

  let dragOver = false;
  let fileLoaded = false;
  let liveMode = false;

  // State for incremental message processing
  const state = {
    agents: {},
    messages: [],
    hooksByParent: new Map(),
    toolResults: new Map()
  };

  function handleEvent(event) {
    processEvent(event, state);

    // Update stores with new state
    agents.set({ ...state.agents });
    allMessages.set([...state.messages]);
  }

  function connectToSSE() {
    const eventSource = new EventSource('/events');

    eventSource.onmessage = (e) => {
      const event = JSON.parse(e.data);
      handleEvent(event);
      if (!fileLoaded) {
        fileLoaded = true;
        liveMode = true;
      }
    };

    eventSource.onerror = (err) => {
      console.error('SSE connection error:', err);
      // Will automatically reconnect
    };

    return eventSource;
  }

  onMount(async () => {
    // Check for URL parameter: ?log=/path/to/file.jsonl
    const urlParams = new URLSearchParams(window.location.search);
    const logPath = urlParams.get('log');

    if (logPath) {
      // URL parameter mode: fetch the specified log file
      try {
        const response = await fetch(logPath);
        if (!response.ok) {
          throw new Error(`Failed to fetch log file: ${response.status} ${response.statusText}`);
        }
        const text = await response.text();
        const { agents: parsedAgents, messages } = parseLog(text);

        agents.set(parsedAgents);
        allMessages.set(messages);
        fileLoaded = true;
        liveMode = false;

        // Set page title from filename
        const filename = logPath.split('/').pop();
        document.title = filename || 'Log Viewer';
      } catch (err) {
        console.error('Failed to load log file from URL:', err);
        alert(`Failed to load log file: ${err.message}`);
      }
      return; // Skip SSE connection
    }

    // Live mode: connect to SSE
    // Fetch session info and set page title
    try {
      const response = await fetch('/session-info');
      const data = await response.json();
      if (data.filename) {
        document.title = data.filename;
      }
    } catch (err) {
      console.error('Failed to fetch session info:', err);
    }

    // Connect to SSE on mount
    const eventSource = connectToSSE();

    // Cleanup on unmount
    return () => {
      eventSource.close();
    };
  });

  function handleDragOver(e) {
    e.preventDefault();
    dragOver = true;
  }

  function handleDragLeave(e) {
    e.preventDefault();
    dragOver = false;
  }

  async function handleDrop(e) {
    e.preventDefault();
    dragOver = false;

    const files = e.dataTransfer.files;
    if (files.length === 0) return;

    const file = files[0];
    if (!file.name.endsWith('.jsonl')) {
      alert('Please drop a .jsonl file');
      return;
    }

    const text = await file.text();
    const { agents: parsedAgents, messages } = parseLog(text);

    agents.set(parsedAgents);
    allMessages.set(messages);
    fileLoaded = true;
    liveMode = false;
  }
</script>

<main>
  {#if !fileLoaded}
    <div
      class="drop-zone"
      class:drag-over={dragOver}
      role="region"
      aria-label="File drop zone"
      on:dragover={handleDragOver}
      on:dragleave={handleDragLeave}
      on:drop={handleDrop}
    >
      <div class="drop-zone-content">
        <h1>Multi-Agent Event Log Viewer</h1>
        <p>Connecting to live session...</p>
        <p style="font-size: 0.9rem; color: #888; margin-top: 1rem;">
          Or drag and drop a .jsonl log file here to view it
        </p>
        <p style="font-size: 0.8rem; color: #aaa; margin-top: 0.5rem;">
          (You can also use ?log=/path/to/file.jsonl)
        </p>
      </div>
    </div>
  {:else}
    <div class="viewer">
      <div class="hierarchy-section">
        <AgentHierarchy />
      </div>
      <div class="panels-section">
        <ChatPanels />
      </div>
    </div>
  {/if}
</main>

<style>
  main {
    width: 100%;
    height: 100vh;
    margin: 0;
    padding: 0;
  }

  .drop-zone {
    width: 100%;
    height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #f5f5f5;
    border: 3px dashed #ccc;
    transition: all 0.3s;
  }

  .drop-zone.drag-over {
    background: #e8f4f8;
    border-color: #4a90e2;
  }

  .drop-zone-content {
    text-align: center;
  }

  .drop-zone-content h1 {
    color: #333;
    margin-bottom: 1rem;
  }

  .drop-zone-content p {
    color: #666;
    font-size: 1.1rem;
  }

  .viewer {
    display: flex;
    flex-direction: column;
    height: 100vh;
  }

  .hierarchy-section {
    border-bottom: 2px solid #ddd;
    padding: 0.5rem 1rem;
    max-height: 20vh;
    overflow-y: auto;
  }

  .panels-section {
    flex: 1;
    overflow: hidden;
  }
</style>
