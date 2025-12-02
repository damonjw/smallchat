<script>
  import { panels, allMessages, agents } from './stores.js';
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

  // Check if a message should be displayed (belongs to at least one panel)
  function messageInAnyPanel(message, panels) {
    return panels.some(panel => messageInPanel(message, panel));
  }

  // Filter messages to only show those that appear in at least one panel
  $: visibleMessages = $allMessages.filter(msg => messageInAnyPanel(msg, $panels));
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

    <!-- Messages grid -->
    <div class="messages-grid">
      {#if visibleMessages.length === 0}
        <div class="empty-state">No messages to display</div>
      {:else}
        {#each visibleMessages as message (message.id)}
          <div class="message-row">
            {#each $panels as panel (panel.id)}
              <div class="message-cell">
                {#if messageInPanel(message, panel)}
                  <Message
                    {message}
                    agentName={$agents[message.agent]?.name}
                    agentId={message.agent}
                    showPrefix={panel.agentIds.length > 1}
                  />
                {/if}
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
</style>
