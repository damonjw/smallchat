<script>
  import { onMount } from 'svelte';
  import { agents, allMessages, logData, panels } from './stores.js';
  import { parseLog } from './logParser.js';
  import AgentHierarchy from './AgentHierarchy.svelte';
  import ChatPanels from './ChatPanels.svelte';

  let dragOver = false;
  let fileLoaded = false;
  let liveMode = false;

  // State for incremental message processing
  let agentsMap = {};
  let messagesList = [];

  function processEvent(event) {
    if (event.event_type === 'agent_created') {
      // Create or update agent
      if (!agentsMap[event.agent]) {
        agentsMap[event.agent] = {
          id: event.agent,
          name: event.name,
          parent: event.parent,
          children: [],
          systemPrompts: []
        };

        // Update parent's children list
        if (event.parent && event.parent !== 'user' && agentsMap[event.parent]) {
          if (!agentsMap[event.parent].children.includes(event.agent)) {
            agentsMap[event.parent].children.push(event.agent);
          }
        }

        // Update store
        agents.set({ ...agentsMap });
      }
    } else if (event.event_type === 'transcript_entry') {
      // Handle system prompts
      if (event.role === 'system' && agentsMap[event.agent]) {
        agentsMap[event.agent].systemPrompts.push(event.content);
        agents.set({ ...agentsMap });
        return;
      }

      // Process messages (only user inputs and assistant utterances without tool_calls)
      if (event.role === 'user' || (event.role === 'assistant' && !event.tool_calls)) {
        // Add message (no global deduplication - will be done per-panel)
        const msg = {
          id: event.message_id,
          agent: event.agent,
          role: event.role,
          content: event.content,
          substance: event.substance
        };

        messagesList.push(msg);

        // Update store
        allMessages.set([...messagesList]);
      }
    }
  }

  function connectToSSE() {
    const eventSource = new EventSource('/events');

    eventSource.onmessage = (e) => {
      const event = JSON.parse(e.data);
      processEvent(event);
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
