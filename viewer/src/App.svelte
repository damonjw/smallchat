<script>
  import { agents, allMessages, logData, panels } from './stores.js';
  import { parseLog, deduplicateMessages } from './logParser.js';
  import AgentHierarchy from './AgentHierarchy.svelte';
  import ChatPanels from './ChatPanels.svelte';

  let dragOver = false;
  let fileLoaded = false;

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
    const dedupedMessages = deduplicateMessages(messages);

    agents.set(parsedAgents);
    allMessages.set(dedupedMessages);
    fileLoaded = true;
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
        <p>Drag and drop a .jsonl log file here to view it</p>
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
