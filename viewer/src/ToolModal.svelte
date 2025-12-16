<script>
  export let toolUseMessage = null;
  export let onClose = () => {};

  let selectedToolCallIndex = null;

  // Automatically select the first tool call when the message changes
  $: if (toolUseMessage && toolUseMessage.tool_calls && toolUseMessage.tool_calls.length > 0) {
    selectedToolCallIndex = 0;
  } else {
    selectedToolCallIndex = null;
  }

  function selectToolCall(index) {
    // Always keep a selection - clicking the same button does nothing
    selectedToolCallIndex = index;
  }

  function handleBackdropClick(e) {
    if (e.target === e.currentTarget) {
      onClose();
    }
  }

  function handleBackdropKeydown(e) {
    // For accessibility: Enter or Space on backdrop should close like a click
    if ((e.key === 'Enter' || e.key === ' ') && e.target === e.currentTarget) {
      e.preventDefault();
      onClose();
    }
  }

  function handleKeydown(e) {
    if (e.key === 'Escape') {
      onClose();
    }
  }

  // Get message fields as separate lines (excluding tool_calls)
  function getMessageFieldLines(msg) {
    if (!msg) return [];

    const lines = [];
    lines.push({ key: 'message_id', value: `"${msg.id}"` });
    lines.push({ key: 'event_type', value: '"transcript_entry"' });
    lines.push({ key: 'agent', value: `"${msg.agent}"` });
    lines.push({ key: 'role', value: '"assistant"' });

    return lines;
  }

  function getSubstanceLine(msg) {
    if (!msg || !msg.substance) return null;
    return { key: 'substance', value: `"${msg.substance}"` };
  }

  // Helper function to format a value (handles nested objects)
  // Uses <b> tags for field names which will be rendered with {@html}
  function formatValue(value, indent = 0) {
    if (value === null || value === undefined) {
      return 'null';
    }
    if (typeof value === 'string') {
      return `"${escapeHtml(value)}"`;
    }
    if (typeof value === 'number' || typeof value === 'boolean') {
      return String(value);
    }
    if (Array.isArray(value)) {
      if (value.length === 0) return '[]';
      const items = value.map(v => formatValue(v, indent + 2));
      return '[\n' + items.map(item => ' '.repeat(indent + 2) + item).join(',\n') + '\n' + ' '.repeat(indent) + ']';
    }
    if (typeof value === 'object') {
      const entries = Object.entries(value);
      if (entries.length === 0) return '{}';
      const lines = entries.map(([k, v]) => {
        const spaces = ' '.repeat(indent + 2);
        const formattedValue = formatValue(v, indent + 2);
        return `${spaces}<b>${escapeHtml(k)}</b>: ${formattedValue}`;
      });
      return '{\n' + lines.join(',\n') + '\n' + ' '.repeat(indent) + '}';
    }
    return String(value);
  }

  // Escape HTML to prevent XSS
  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  // Format tool call details as structured data for rendering
  function getToolCallLines(toolCall) {
    if (!toolCall) return [];

    // Show the raw fields from the tool call (without the result field)
    const { result, ...rawToolCall } = toolCall;

    return Object.entries(rawToolCall).map(([key, value]) => ({
      key,
      value: formatValue(value, 0)
    }));
  }

  // Format tool result as structured data for rendering
  function getToolResultLines(result) {
    if (!result) return [];

    return Object.entries(result).map(([key, value]) => ({
      key,
      value: formatValue(value, 0)
    }));
  }

  $: selectedToolCall = selectedToolCallIndex !== null ? toolUseMessage?.tool_calls[selectedToolCallIndex] : null;
</script>

<svelte:window on:keydown={handleKeydown} />

{#if toolUseMessage}
  <div class="modal-backdrop" on:click={handleBackdropClick} on:keydown={handleBackdropKeydown} role="dialog" aria-modal="true" tabindex="-1">
    <div class="modal-content">
      <div class="modal-header">
        <h2>Tool Usage Details</h2>
        <button class="close-btn" on:click={onClose} aria-label="Close">&times;</button>
      </div>
      <div class="modal-body">
        <!-- Raw message fields with inline tool buttons -->
        <div class="message-fields">
          <div class="fields-display">
            {#each getMessageFieldLines(toolUseMessage) as line}
              <div class="field-line"><span class="field-name">{line.key}</span>: {line.value},</div>
            {/each}
            <div class="field-line">
              <span class="field-name">tool_calls</span>: [
              {#each toolUseMessage.tool_calls as toolCall, index (toolCall.id)}
                <button
                  class="inline-tool-button"
                  class:selected={selectedToolCallIndex === index}
                  on:click={() => selectToolCall(index)}
                >
                  {toolCall.function?.name || 'unknown'}
                </button>{#if index < toolUseMessage.tool_calls.length - 1}<span>, </span>{/if}
              {/each}
              <span>]{getSubstanceLine(toolUseMessage) ? ',' : ''}</span>
            </div>
            {#if getSubstanceLine(toolUseMessage)}
              {@const substanceLine = getSubstanceLine(toolUseMessage)}
              <div class="field-line"><span class="field-name">{substanceLine.key}</span>: {substanceLine.value}</div>
            {/if}
          </div>
        </div>

        <!-- Selected tool call details -->
        {#if selectedToolCall}
          <hr class="divider" />

          <div class="tool-call-details">
            <div class="details-display">
              {#each getToolCallLines(selectedToolCall) as line, idx}
                <div class="detail-line"><span class="field-name">{line.key}</span>: {@html line.value}{idx < getToolCallLines(selectedToolCall).length - 1 ? ',' : ''}</div>
              {/each}
            </div>
          </div>

          {#if selectedToolCall.result}
            <hr class="divider" />

            <div class="tool-result-details">
              <div class="details-display">
                {#each getToolResultLines(selectedToolCall.result) as line, idx}
                  <div class="detail-line"><span class="field-name">{line.key}</span>: {@html line.value}{idx < getToolResultLines(selectedToolCall.result).length - 1 ? ',' : ''}</div>
                {/each}
              </div>
            </div>
          {/if}
        {/if}
      </div>
    </div>
  </div>
{/if}

<style>
  .modal-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.7);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    padding: 2rem;
  }

  .modal-content {
    background: white;
    border-radius: 8px;
    max-width: 900px;
    width: 100%;
    max-height: 90vh;
    display: flex;
    flex-direction: column;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
  }

  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1.5rem;
    border-bottom: 1px solid #ddd;
  }

  .modal-header h2 {
    margin: 0;
    font-size: 1.5rem;
  }

  .close-btn {
    background: none;
    border: none;
    font-size: 2rem;
    cursor: pointer;
    color: #666;
    line-height: 1;
    padding: 0;
    width: 2rem;
    height: 2rem;
  }

  .close-btn:hover {
    color: #d32f2f;
  }

  .modal-body {
    overflow-y: auto;
    padding: 1.5rem;
  }

  .message-fields {
    margin-bottom: 1rem;
  }

  .fields-display {
    font-family: 'Courier New', Courier, monospace;
    font-size: 0.9rem;
    margin: 0;
    margin-bottom: 1rem;
  }

  .field-line {
    line-height: 1.5;
  }

  .field-name {
    font-weight: bold;
  }

  .inline-tool-button {
    background: transparent;
    color: #333;
    border: 1px solid #999;
    padding: 0px 3px;
    border-radius: 2px;
    cursor: pointer;
    font-family: 'Courier New', Courier, monospace;
    font-size: 0.9rem;
    font-weight: normal;
    transition: all 0.15s;
    display: inline;
    margin: 0;
    vertical-align: baseline;
  }

  .inline-tool-button:hover {
    background: #e8e8e8;
    border-color: #666;
  }

  .inline-tool-button.selected {
    background: #007bff;
    color: white;
    border-color: #0056b3;
  }

  .divider {
    border: none;
    border-top: 1px solid #ccc;
    margin: 1rem 0;
  }

  .tool-call-details,
  .tool-result-details {
    margin: 1rem 0;
  }

  .details-display {
    font-family: 'Courier New', Courier, monospace;
    font-size: 0.9rem;
    margin: 0;
  }

  .detail-line {
    line-height: 1.5;
    white-space: pre-wrap;
  }
</style>
