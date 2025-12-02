<script>
  import { agents } from './stores.js';
  import AgentNode from './AgentNode.svelte';

  // Find root agents (those with parent='user' or no parent in the tree)
  $: rootAgents = Object.values($agents).filter(a => a.parent === 'user');
</script>

<div class="hierarchy">
  {#if rootAgents.length === 0}
    <p class="empty">No agents found in log</p>
  {:else}
    {#each rootAgents as agent (agent.id)}
      <AgentNode {agent} />
    {/each}
  {/if}
</div>

<style>
  .hierarchy {
    font-family: monospace;
  }

  .empty {
    color: #999;
    font-style: italic;
  }
</style>
