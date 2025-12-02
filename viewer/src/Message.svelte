<script>
  import { getAgentTextColor } from './colors.js';

  export let message;
  export let agentName = '';
  export let agentId = '';
  export let showPrefix = false;

  $: isUser = message.role === 'user';
  $: isAssistant = message.role === 'assistant';
  $: colorKey = agentId && agentName ? (agentId + '_' + agentName) : agentId;
  $: textColor = colorKey ? getAgentTextColor(colorKey) : '#333';
</script>

<div class="message" class:user={isUser} class:assistant={isAssistant}>
  {#if isAssistant && showPrefix && agentName}
    <div class="message-content">
      <span class="agent-prefix" style="color: {textColor};">[{agentName}]:</span>
      {message.content}
    </div>
  {:else}
    <div class="message-content">
      {message.content}
    </div>
  {/if}
</div>

<style>
  .message {
    margin-bottom: 0.5rem;
    word-wrap: break-word;
  }

  .message.user {
    background: #f0f0f0;
    padding: 0.75rem 1rem;
    border-radius: 8px;
    max-width: 90%;
    margin-left: auto;
    margin-right: 0;
  }

  .message.assistant {
    /* Plain text, full width, no background */
    width: 100%;
  }

  .message-content {
    white-space: pre-wrap;
    line-height: 1.5;
  }

  .agent-prefix {
    font-weight: 700;
    margin-right: 0.5rem;
  }
</style>
