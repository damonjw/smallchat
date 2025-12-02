/**
 * Parse a .jsonl log file and extract agents and messages
 */

export function parseLog(text) {
  const lines = text.split('\n').filter(line => line.trim());
  const events = lines.map(line => JSON.parse(line));

  const agents = {};
  const messages = [];

  // First pass: create all agents
  for (const event of events) {
    if (event.event_type === 'agent_created') {
      agents[event.agent] = {
        id: event.agent,
        name: event.name,
        parent: event.parent,
        children: []
      };
    }
  }

  // Second pass: build parent-child relationships
  for (const agent of Object.values(agents)) {
    if (agent.parent && agent.parent !== 'user' && agents[agent.parent]) {
      agents[agent.parent].children.push(agent.id);
    }
  }

  // Third pass: extract messages
  for (const event of events) {
    if (event.event_type === 'transcript_entry') {
      // Only show user messages (inputs) and assistant messages without tool_calls (utterances)
      if (event.role === 'user') {
        messages.push({
          id: event.message_id,
          agent: event.agent,
          role: 'user',
          content: event.content,
          substance: event.substance
        });
      } else if (event.role === 'assistant' && !event.tool_calls) {
        messages.push({
          id: event.message_id,
          agent: event.agent,
          role: 'assistant',
          content: event.content,
          substance: event.substance
        });
      }
    }
  }

  return { agents, messages };
}

/**
 * Deduplicate messages based on substance and content
 */
export function deduplicateMessages(messages) {
  const seen = new Set();
  const seenSubstance = new Set();
  const result = [];

  for (const msg of messages) {
    // Check substance-based deduplication
    if (msg.substance) {
      if (seenSubstance.has(msg.substance)) {
        continue; // Skip this message
      }
      seenSubstance.add(msg.id);
    }

    // Check content-based deduplication
    const contentKey = `${msg.role}:${msg.content}`;
    if (seen.has(contentKey)) {
      continue; // Skip duplicate content
    }

    seen.add(contentKey);
    if (!msg.substance) {
      seenSubstance.add(msg.id);
    }

    result.push(msg);
  }

  return result;
}
