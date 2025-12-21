<script>
  import { agents } from './stores.js';
  import { getAgentBadgeColor, getAgentBorderColor } from './colors.js';

  export let agent;
  export let depth = 0;
  export let inline = false;

  let expanded = true;

  $: hookCount = agent.hookCount || 0;
  $: hooks = (agent.hooks || []).map(hookId => $agents[hookId]).filter(Boolean);

  function handleDragStart(e) {
    e.dataTransfer.effectAllowed = 'copy';
    e.dataTransfer.setData('application/json', JSON.stringify({ agentId: agent.id }));
  }

  function handleHookDragStart(e, hookAgentId) {
    e.dataTransfer.effectAllowed = 'copy';
    e.dataTransfer.setData('application/json', JSON.stringify({ agentId: hookAgentId }));
  }

  function toggleExpand() {
    expanded = !expanded;
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      toggleExpand();
    }
  }

  $: children = agent.children.map(childId => $agents[childId]).filter(Boolean);
  $: hasChildren = children.length > 0;
  $: hasSingleChild = children.length === 1;
  $: hasMultipleChildren = children.length > 1;
  $: colorKey = agent.id + '_' + agent.name;
  $: badgeColor = getAgentBadgeColor(colorKey);
  $: borderColor = getAgentBorderColor(colorKey);
</script>

<div class="agent-node" class:inline style="margin-left: {inline ? 0 : depth * 20}px">
  <div class="agent-item">
    {#if !inline}
      {#if hasMultipleChildren}
        <span class="toggle" role="button" tabindex="0" on:click={toggleExpand} on:keydown={handleKeyDown}>
          {expanded ? '▼' : '▶'}
        </span>
      {:else}
        <span class="toggle-spacer"></span>
      {/if}
    {/if}

    <span
      class="agent-badge"
      role="button"
      tabindex="0"
      draggable="true"
      on:dragstart={handleDragStart}
      style="background-color: {badgeColor}; border-color: {borderColor};"
    >
      {agent.name}
    </span>

    {#each hooks as hook (hook.id)}
      <span
        class="hook-indicator"
        title="Hook: {hook.name}"
        role="button"
        tabindex="0"
        draggable="true"
        on:dragstart={(e) => handleHookDragStart(e, hook.id)}
      >
        H
      </span>
    {/each}

    {#if hasSingleChild}
      <span class="separator">▸</span>
      <svelte:self agent={children[0]} depth={depth} inline={true} />
    {/if}
  </div>

  {#if expanded && hasMultipleChildren}
    {#each children as child (child.id)}
      <svelte:self agent={child} depth={depth + 1} />
    {/each}
  {/if}
</div>

<style>
  .agent-node {
    user-select: none;
  }

  .agent-node.inline {
    display: inline-flex;
    align-items: center;
  }

  .agent-item {
    display: flex;
    align-items: center;
    padding: 0.15rem 0;
    gap: 0.5rem;
  }

  /* Create slight overlap for vertical children only */
  .agent-node:not(.inline) :global(.agent-node:not(.inline)) {
    margin-top: -0.2rem;
  }

  .toggle {
    cursor: pointer;
    width: 20px;
    display: inline-block;
    text-align: center;
    font-size: 0.8rem;
    user-select: none;
  }

  .toggle-spacer {
    width: 20px;
    display: inline-block;
  }

  .separator {
    color: #999;
    font-size: 0.9rem;
    margin: 0 0.3rem;
  }

  .agent-badge {
    display: inline-flex;
    align-items: center;
    padding: 0.1rem 0.75rem;
    border-radius: 12px;
    font-size: 0.9rem;
    font-weight: 500;
    cursor: move;
    border: 1px solid;
    transition: transform 0.2s;
  }

  .agent-badge:hover {
    transform: translateY(-1px);
  }

  .hook-indicator {
    margin-left: 0.4rem;
    font-size: 0.75rem;
    font-weight: 600;
    color: #666;
    opacity: 0.8;
    cursor: move;
    user-select: none;
  }
</style>
