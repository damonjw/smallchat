<script>
  import { panels, allMessages, agents } from './stores.js';
  import { deduplicateMessages } from './logParser.js';
  import Message from './Message.svelte';
  import { getAgentBadgeColor, getAgentBorderColor } from './colors.js';

  let nextPanelId = 1;
  let hoveredDivider = null; // Track which divider is being hovered during drag
  let hoveredPanel = null; // Track which panel is being hovered during drag
  let dragSourcePanel = null; // Track which panel an agent badge is being dragged from

  function removePanel(panelId) {
    panels.update(p => p.filter(panel => panel.id !== panelId));
  }

  function createNewPanel(agentId) {
    const newPanel = { id: nextPanelId++, agentIds: [agentId] };
    panels.update(p => [...p, newPanel]);
  }

  function insertPanelAtPosition(agentId, position) {
    const newPanel = { id: nextPanelId++, agentIds: [agentId] };
    panels.update(p => {
      const newPanels = [...p];
      newPanels.splice(position, 0, newPanel);
      return newPanels;
    });
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

  function handleBadgeDragStart(panelId, agentId, e) {
    e.stopPropagation(); // Prevent panel drag handlers from firing
    dragSourcePanel = panelId;
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('application/json', JSON.stringify({ agentId, fromPanel: panelId }));
  }

  function handleBadgeDragEnd(panelId, agentId, e) {
    // If drop was not successful (dropEffect is 'none'), remove the agent from the panel
    if (e.dataTransfer.dropEffect === 'none') {
      removeAgentFromPanel(panelId, agentId);
    }
    dragSourcePanel = null;
  }

  function handlePanelDrop(panelId, e) {
    e.preventDefault();
    e.stopPropagation();
    hoveredPanel = null;
    const data = JSON.parse(e.dataTransfer.getData('application/json'));
    if (data.agentId) {
      // If moving from another panel, remove from source first
      if (data.fromPanel !== undefined && data.fromPanel !== panelId) {
        removeAgentFromPanel(data.fromPanel, data.agentId);
      }
      addAgentToPanel(panelId, data.agentId);
    }
  }

  function handlePanelDragOver(panelId, e) {
    e.preventDefault();
    e.stopPropagation();
    hoveredPanel = panelId;
  }

  function handlePanelDragLeave(e) {
    e.preventDefault();
    e.stopPropagation();
    hoveredPanel = null;
  }

  function handleDividerDrop(position, e) {
    e.preventDefault();
    e.stopPropagation();
    hoveredDivider = null;
    const data = JSON.parse(e.dataTransfer.getData('application/json'));
    if (data.agentId) {
      // If moving from a panel, remove from source first
      if (data.fromPanel !== undefined) {
        removeAgentFromPanel(data.fromPanel, data.agentId);
      }
      insertPanelAtPosition(data.agentId, position);
    }
  }

  function handleEmptyStateDrop(e) {
    e.preventDefault();
    const data = JSON.parse(e.dataTransfer.getData('application/json'));
    if (data.agentId) {
      // If moving from a panel, remove from source first
      if (data.fromPanel !== undefined) {
        removeAgentFromPanel(data.fromPanel, data.agentId);
      }
      createNewPanel(data.agentId);
    }
  }

  function handleDividerDragOver(dividerId, e) {
    e.preventDefault();
    e.stopPropagation();
    hoveredDivider = dividerId;
  }

  function handleDividerDragLeave(e) {
    e.preventDefault();
    hoveredDivider = null;
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
  {#if $panels.length === 0}
    <!-- Empty state -->
    <div class="empty-state-container">
      <div
        class="empty-state-header"
        role="region"
        aria-label="Drop zone for first panel"
        on:dragover={(e) => e.preventDefault()}
        on:drop={handleEmptyStateDrop}
      >
        <div class="empty-state-text">Drag an agent here to view its transcript</div>
      </div>
    </div>
  {:else}
    <!-- Shared scroll container for both headers and messages -->
    <div class="messages-scroll-container">
      <!-- Sticky panel headers -->
      <div class="panel-headers">
        {#each $panels as panel, index (panel.id)}
          <!-- Left divider (before first panel or between panels) -->
          <div
            class="divider-drop-zone"
            class:hovered={hoveredDivider === `divider-${index}`}
            role="region"
            aria-label="Drop zone to insert panel"
            on:dragover={(e) => handleDividerDragOver(`divider-${index}`, e)}
            on:dragleave={handleDividerDragLeave}
            on:drop={(e) => handleDividerDrop(index, e)}
          >
          </div>

          <!-- Panel header -->
          <div
            class="panel-header"
            class:hovered={hoveredPanel === panel.id}
            role="region"
            aria-label="Panel header drop zone"
            on:dragover={(e) => handlePanelDragOver(panel.id, e)}
            on:dragleave={handlePanelDragLeave}
            on:drop={(e) => handlePanelDrop(panel.id, e)}
          >
            <div class="agent-badges">
              {#each panel.agentIds as agentId (agentId)}
                {@const agent = $agents[agentId]}
                {#if agent}
                  {@const colorKey = agentId + '_' + agent.name}
                  <span
                    class="agent-badge"
                    role="button"
                    tabindex="0"
                    draggable="true"
                    on:dragstart={(e) => handleBadgeDragStart(panel.id, agentId, e)}
                    on:dragend={(e) => handleBadgeDragEnd(panel.id, agentId, e)}
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

        <!-- Right divider (after last panel) -->
        <div
          class="divider-drop-zone"
          class:hovered={hoveredDivider === `divider-${$panels.length}`}
          role="region"
          aria-label="Drop zone to insert panel"
          on:dragover={(e) => handleDividerDragOver(`divider-${$panels.length}`, e)}
          on:dragleave={handleDividerDragLeave}
          on:drop={(e) => handleDividerDrop($panels.length, e)}
        >
        </div>
      </div>

      <!-- System prompts row -->
      <div class="system-prompts-row">
        {#each $panels as panel, index (panel.id)}
          <!-- Left divider drop zone -->
          <div
            class="divider-drop-zone"
            class:hovered={hoveredDivider === `divider-${index}`}
            role="region"
            aria-label="Drop zone to insert panel"
            on:dragover={(e) => handleDividerDragOver(`divider-${index}`, e)}
            on:dragleave={handleDividerDragLeave}
            on:drop={(e) => handleDividerDrop(index, e)}
          ></div>

          <!-- System prompts cell -->
          <div
            class="system-prompts-cell"
            role="region"
            aria-label="Panel drop zone"
            on:dragover={(e) => handlePanelDragOver(panel.id, e)}
            on:dragleave={handlePanelDragLeave}
            on:drop={(e) => handlePanelDrop(panel.id, e)}
          >
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

        <!-- Right divider drop zone -->
        <div
          class="divider-drop-zone"
          class:hovered={hoveredDivider === `divider-${$panels.length}`}
          role="region"
          aria-label="Drop zone to insert panel"
          on:dragover={(e) => handleDividerDragOver(`divider-${$panels.length}`, e)}
          on:dragleave={handleDividerDragLeave}
          on:drop={(e) => handleDividerDrop($panels.length, e)}
        ></div>
      </div>

      <!-- Messages grid -->
      <div class="messages-grid">
        {#if rowGroups.length === 0}
          <div class="empty-state">No messages to display</div>
        {:else}
          {#each rowGroups as rowGroup, rowIndex (rowGroup.substance || `row-${rowIndex}`)}
            <div class="message-row">
              {#each $panels as panel, index (panel.id)}
                <!-- Left divider drop zone -->
                <div
                  class="divider-drop-zone"
                  class:hovered={hoveredDivider === `divider-${index}`}
                  role="region"
                  aria-label="Drop zone to insert panel"
                  on:dragover={(e) => handleDividerDragOver(`divider-${index}`, e)}
                  on:dragleave={handleDividerDragLeave}
                  on:drop={(e) => handleDividerDrop(index, e)}
                ></div>

                <!-- Message cell -->
                <div
                  class="message-cell"
                  role="region"
                  aria-label="Panel drop zone"
                  on:dragover={(e) => handlePanelDragOver(panel.id, e)}
                  on:dragleave={handlePanelDragLeave}
                  on:drop={(e) => handlePanelDrop(panel.id, e)}
                >
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

              <!-- Right divider drop zone -->
              <div
                class="divider-drop-zone"
                class:hovered={hoveredDivider === `divider-${$panels.length}`}
                role="region"
                aria-label="Drop zone to insert panel"
                on:dragover={(e) => handleDividerDragOver(`divider-${$panels.length}`, e)}
                on:dragleave={handleDividerDragLeave}
                on:drop={(e) => handleDividerDrop($panels.length, e)}
              ></div>
            </div>
          {/each}
        {/if}
      </div>
    </div>
  {/if}
</div>

<style>
  .panels-container {
    display: flex;
    flex-direction: column;
    height: 100%;
  }

  .empty-state-container {
    display: flex;
    flex-direction: column;
    height: 100%;
  }

  .empty-state-header {
    position: sticky;
    top: 0;
    z-index: 10;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0.75rem;
    border-bottom: 2px solid #ddd;
    background: #f9f9f9;
    min-height: 3rem;
  }

  .empty-state-text {
    color: #999;
    font-style: italic;
    font-size: 1rem;
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

  .divider-drop-zone {
    min-width: 2em;
    width: 2em;
    background: transparent;
    position: relative;
    transition: background 0.2s;
    cursor: pointer;
  }

  .divider-drop-zone::before {
    content: '';
    position: absolute;
    left: 50%;
    top: 0;
    bottom: 0;
    width: 1px;
    background: #333;
    transform: translateX(-50%);
  }

  .divider-drop-zone.hovered {
    background: rgba(173, 216, 230, 0.5); /* Light blue translucent */
  }

  .panel-header {
    flex: 1;
    min-width: 400px;
    padding: 0.75rem;
    transition: background 0.2s;
  }

  .panel-header.hovered {
    background: rgba(173, 216, 230, 0.5); /* Light blue translucent */
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
    cursor: move;
    user-select: none;
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
  }

  .system-prompt-box {
    border: 2pt dashed #000;
    padding: 0.75rem;
    margin-bottom: 0.5rem;
    background: #ffffff;
  }

  .system-prompt-agent-name {
    font-weight: bold;
    margin-bottom: 0.5rem;
    color: #333;
  }

  .system-prompt-content {
    white-space: pre-wrap;
    font-family: monospace, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 0.8rem;
    line-height: 1.5;
    color: #333;
  }
</style>
