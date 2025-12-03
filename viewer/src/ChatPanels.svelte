<script>
  import { panels, allMessages, agents } from './stores.js';
  import { deduplicateMessages } from './logParser.js';
  import Message from './Message.svelte';
  import { getAgentBadgeColor, getAgentBorderColor } from './colors.js';

  let nextPanelId = 1;

  function removePanel(panelId) {
    panels.update(p => p.filter(panel => panel.id !== panelId));
  }

  function createNewPanel(agentId) {
    const newPanel = { id: nextPanelId++, agentIds: [agentId] };
    panels.update(p => [...p, newPanel]);
  }

  function addAgentToPanel(panelId, agentId) {
    panels.update(p => p.map(panel => {
      if (panel.id === panelId) {
        if (!panel.agentIds.includes(agentId)) {
          return { ...panel, agentIds: [...panel.agentIds, agentId] };
        }
      }
      return panel;
    }));
  }

  function removeAgentFromPanel(panelId, agentId) {
    panels.update(p => {
      const updated = p.map(panel => {
        if (panel.id === panelId) {
          return { ...panel, agentIds: panel.agentIds.filter(id => id !== agentId) };
        }
        return panel;
      });
      // Remove empty panels
      return updated.filter(panel => panel.agentIds.length > 0);
    });
  }

  function handlePanelDrop(panelId, e) {
    e.preventDefault();
    const data = JSON.parse(e.dataTransfer.getData('application/json'));
    if (data.agentId) {
      addAgentToPanel(panelId, data.agentId);
    }
  }

  function handleNewPanelDrop(e) {
    e.preventDefault();
    const data = JSON.parse(e.dataTransfer.getData('application/json'));
    if (data.agentId) {
      createNewPanel(data.agentId);
    }
  }

  // Check if a message belongs to a panel (agent is sender or receiver)
  function messageInPanel(message, panel) {
    return panel.agentIds.includes(message.agent);
  }

  // Create per-panel deduplicated message lists
  function getPerPanelMessages(allMessages, panels) {
    const panelMessages = new Map();

    for (const panel of panels) {
      // Get messages for this panel's agents
      const panelMsgs = allMessages.filter(msg => messageInPanel(msg, panel));
      // Deduplicate per panel
      const dedupedMsgs = deduplicateMessages(panelMsgs);
      panelMessages.set(panel.id, new Set(dedupedMsgs.map(m => m.id)));
    }

    return panelMessages;
  }

  // Create row groups where messages with same substance are aligned
  function createRowGroups(allMessages, panelMessages, panels) {
    const rowGroups = [];
    const substanceToRow = new Map(); // substance -> row index
    const messageIdToRow = new Map(); // message id -> row index
    const processedMessageIds = new Set();

    for (const msg of allMessages) {
      // Skip if already processed
      if (processedMessageIds.has(msg.id)) continue;

      // Check if this message is visible in any panel
      let isVisible = false;
      for (const panel of panels) {
        if (panelMessages.get(panel.id)?.has(msg.id)) {
          isVisible = true;
          break;
        }
      }
      if (!isVisible) continue;

      let rowIndex;

      if (msg.substance) {
        // Check if we already have a row for this substance
        if (substanceToRow.has(msg.substance)) {
          rowIndex = substanceToRow.get(msg.substance);
          rowGroups[rowIndex].messages.push(msg);
        }
        // Check if there's a message with id matching this substance
        else if (messageIdToRow.has(msg.substance)) {
          rowIndex = messageIdToRow.get(msg.substance);
          rowGroups[rowIndex].messages.push(msg);
          // Also map this substance to the row
          substanceToRow.set(msg.substance, rowIndex);
        }
        else {
          // Create new row for this substance
          rowIndex = rowGroups.length;
          substanceToRow.set(msg.substance, rowIndex);
          rowGroups.push({
            substance: msg.substance,
            messages: [msg]
          });
        }
      } else {
        // No substance - create new row
        rowIndex = rowGroups.length;
        rowGroups.push({
          substance: null,
          messages: [msg]
        });
        // Map this message's id to the row so other messages can reference it
        messageIdToRow.set(msg.id, rowIndex);
      }

      processedMessageIds.add(msg.id);
    }

    return rowGroups;
  }

  // Reactive: compute per-panel deduplicated messages
  $: panelMessages = getPerPanelMessages($allMessages, $panels);

  // Reactive: create row groups with substance-based alignment
  $: rowGroups = createRowGroups($allMessages, panelMessages, $panels);
</script>

<div class="panels-container">
  <!-- Shared scroll container for both headers and messages -->
  <div class="messages-scroll-container">
    <!-- Sticky panel headers -->
    <div class="panel-headers">
      {#each $panels as panel (panel.id)}
        <div
          class="panel-header"
          role="region"
          aria-label="Panel header drop zone"
          on:dragover={(e) => e.preventDefault()}
          on:drop={(e) => handlePanelDrop(panel.id, e)}
        >
          <div class="agent-badges">
            {#each panel.agentIds as agentId (agentId)}
              {@const agent = $agents[agentId]}
              {#if agent}
                {@const colorKey = agentId + '_' + agent.name}
                <span
                  class="agent-badge"
                  style="background-color: {getAgentBadgeColor(colorKey)}; border-color: {getAgentBorderColor(colorKey)};"
                >
                  {agent.name}
                  <button class="remove-btn" on:click={() => removeAgentFromPanel(panel.id, agentId)}>×</button>
                </span>
              {/if}
            {/each}
          </div>
        </div>
      {/each}
      <div
        class="new-panel-drop-zone"
        role="region"
        aria-label="Drop to create new panel"
        on:dragover={(e) => e.preventDefault()}
        on:drop={handleNewPanelDrop}
      >
        <div class="drop-hint">⊕</div>
      </div>
    </div>

    <!-- System prompts row -->
    <div class="system-prompts-row">
      {#each $panels as panel (panel.id)}
        <div class="system-prompts-cell">
          {#if panel.agentIds.length === 1}
            <!-- Single agent: show system prompt without agent name -->
            {@const agentId = panel.agentIds[0]}
            {@const agent = $agents[agentId]}
            {#if agent && agent.systemPrompts && agent.systemPrompts.length > 0}
              {#each agent.systemPrompts as prompt}
                <div class="system-prompt-box">
                  <div class="system-prompt-content">{prompt}</div>
                </div>
              {/each}
            {/if}
          {:else}
            <!-- Multiple agents: show each agent's system prompt with name -->
            {#each panel.agentIds as agentId (agentId)}
              {@const agent = $agents[agentId]}
              {#if agent && agent.systemPrompts && agent.systemPrompts.length > 0}
                {#each agent.systemPrompts as prompt}
                  <div class="system-prompt-box">
                    <div class="system-prompt-agent-name">{agent.name}</div>
                    <div class="system-prompt-content">{prompt}</div>
                  </div>
                {/each}
              {/if}
            {/each}
          {/if}
        </div>
      {/each}
      <div class="message-cell-spacer"></div>
    </div>

    <!-- Messages grid -->
    <div class="messages-grid">
      {#if rowGroups.length === 0}
        <div class="empty-state">No messages to display</div>
      {:else}
        {#each rowGroups as rowGroup, rowIndex (rowGroup.substance || `row-${rowIndex}`)}
          <div class="message-row">
            {#each $panels as panel (panel.id)}
              <div class="message-cell">
                {#each rowGroup.messages as message (message.id)}
                  {#if panelMessages.get(panel.id)?.has(message.id)}
                    <Message
                      {message}
                      agentName={$agents[message.agent]?.name}
                      agentId={message.agent}
                      showPrefix={panel.agentIds.length > 1}
                    />
                  {/if}
                {/each}
              </div>
            {/each}
            <div class="message-cell-spacer"></div>
          </div>
        {/each}
      {/if}
    </div>
  </div>
</div>

<style>
  .panels-container {
    display: flex;
    flex-direction: column;
    height: 100%;
  }

  .messages-scroll-container {
    flex: 1;
    overflow-y: auto;
    overflow-x: auto;
  }

  .panel-headers {
    position: sticky;
    top: 0;
    z-index: 10;
    display: flex;
    border-bottom: 2px solid #ddd;
    background: #f9f9f9;
  }

  .panel-header {
    flex: 1;
    min-width: 400px;
    padding: 0.75rem;
    border-right: 1px solid #ddd;
  }

  .agent-badges {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
  }

  .agent-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.1rem 0.75rem;
    border-radius: 12px;
    font-size: 0.9rem;
    font-weight: 500;
    border: 1px solid;
  }

  .remove-btn {
    background: none;
    border: none;
    cursor: pointer;
    font-size: 1.2rem;
    line-height: 1;
    padding: 0;
    color: #666;
  }

  .remove-btn:hover {
    color: #d32f2f;
  }

  .new-panel-drop-zone {
    min-width: 4em;
    width: 4em;
    border-right: 1px solid #ddd;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0.5rem;
    transition: background 0.2s;
  }

  .new-panel-drop-zone:hover {
    background: #f0f8ff;
  }

  .drop-hint {
    color: #999;
    font-size: 2rem;
    line-height: 1;
    text-align: center;
  }

  .messages-grid {
    min-width: fit-content;
  }

  .message-row {
    display: flex;
    min-height: 40px;
  }

  .message-cell {
    flex: 1;
    min-width: 400px;
    padding: 0.5rem 1rem;
    border-right: 1px solid #e0e0e0;
  }

  .message-cell-spacer {
    min-width: 4em;
    width: 4em;
    border-right: 1px solid #e0e0e0;
  }

  .empty-state {
    padding: 2rem;
    text-align: center;
    color: #999;
    font-style: italic;
  }

  .system-prompts-row {
    display: flex;
    min-height: fit-content;
  }

  .system-prompts-cell {
    flex: 1;
    min-width: 400px;
    padding: 0.5rem 1rem;
    border-right: 1px solid #e0e0e0;
  }

  .system-prompt-box {
    border: 2px solid #000;
    padding: 0.75rem;
    margin-bottom: 0.5rem;
    background: #f5f5f5;
  }

  .system-prompt-agent-name {
    font-weight: bold;
    margin-bottom: 0.5rem;
    color: #333;
  }

  .system-prompt-content {
    white-space: pre-wrap;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 0.9rem;
    line-height: 1.5;
    color: #333;
  }
</style>
