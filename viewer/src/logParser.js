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
        children: [],
        systemPrompts: []
      };
    }
  }

  // Second pass: build parent-child relationships
  for (const agent of Object.values(agents)) {
    if (agent.parent && agent.parent !== 'user' && agents[agent.parent]) {
      agents[agent.parent].children.push(agent.id);
    }
  }

  // Third pass: build a map of tool results by tool_call_id
  const toolResults = new Map(); // tool_call_id -> tool result event
  for (const event of events) {
    if (event.event_type === 'transcript_entry' && event.role === 'tool' && event.tool_call_id) {
      toolResults.set(event.tool_call_id, event);
    }
  }

  // Fourth pass: extract messages and system prompts
  for (const event of events) {
    if (event.event_type === 'transcript_entry') {
      // Extract system prompts
      if (event.role === 'system' && agents[event.agent]) {
        agents[event.agent].systemPrompts.push(event.content);
      }
      // User messages (inputs)
      else if (event.role === 'user') {
        messages.push({
          id: event.message_id,
          agent: event.agent,
          role: 'user',
          content: event.content,
          substance: event.substance
        });
      }
      // Assistant messages with tool_calls
      else if (event.role === 'assistant' && event.tool_calls) {
        // Attach tool results to each tool call
        const toolCallsWithResults = event.tool_calls.map(toolCall => {
          const result = toolResults.get(toolCall.id);
          const toolCallCopy = { ...toolCall };
          if (result) {
            // Add result field, excluding specified fields
            toolCallCopy.result = {
              role: result.role,
              content: result.content,
              name: result.name
            };
          }
          return toolCallCopy;
        });

        messages.push({
          id: event.message_id,
          agent: event.agent,
          role: 'assistant_tool_use',
          tool_calls: toolCallsWithResults,
          substance: event.substance
        });
      }
      // Assistant messages without tool_calls (utterances)
      else if (event.role === 'assistant' && !event.tool_calls) {
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
      seenSubstance.add(msg.substance);
    }

    // Check content-based deduplication
    // For tool_use messages, use the message id since they don't have content
    const contentKey = msg.role === 'assistant_tool_use'
      ? `${msg.role}:${msg.id}`
      : `${msg.role}:${msg.content}`;
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
