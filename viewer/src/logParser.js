/**
 * Parse a .jsonl log file and extract agents and messages
 */

/**
 * Process a single event and update state incrementally
 */
export function processEvent(event, state) {
  const { agents, messages, hooksByParent, toolResults } = state;

  if (event.event_type === 'agent_created') {
    // Create agent if it doesn't exist
    if (!agents[event.agent]) {
      agents[event.agent] = {
        id: event.agent,
        name: event.name,
        parent: event.parent,
        children: [],
        systemPrompts: [],
        isHook: event.role === 'hook',
        hookCount: 0,
        hooks: []
      };

      // Track hooks by parent agent
      if (event.role === 'hook' && event.parent) {
        if (!hooksByParent.has(event.parent)) {
          hooksByParent.set(event.parent, []);
        }
        hooksByParent.get(event.parent).push(event.agent);

        // Update parent's hookCount and hooks array
        if (agents[event.parent]) {
          const hooks = hooksByParent.get(event.parent) || [];
          agents[event.parent].hookCount = hooks.length;
          agents[event.parent].hooks = hooks;
        }
      }

      // Update parent's children list (excluding hooks)
      if (event.parent && event.parent !== 'user' && agents[event.parent] && event.role !== 'hook') {
        if (!agents[event.parent].children.includes(event.agent)) {
          agents[event.parent].children.push(event.agent);
        }
      }

      // If this agent was created and already has hooks waiting, update its hookCount
      const existingHooks = hooksByParent.get(event.agent) || [];
      if (existingHooks.length > 0) {
        agents[event.agent].hookCount = existingHooks.length;
        agents[event.agent].hooks = existingHooks;
      }
    }
  } else if (event.event_type === 'transcript_entry') {
    // Handle system prompts
    if (event.role === 'system' && agents[event.agent]) {
      agents[event.agent].systemPrompts.push(event.content);
      return;
    }

    // Store tool results for later attachment
    if (event.role === 'tool' && event.tool_call_id) {
      toolResults.set(event.tool_call_id, event);
      return;
    }

    // User messages (inputs)
    if (event.role === 'user') {
      const msg = {
        id: event.message_id,
        agent: event.agent,
        role: 'user',
        content: event.content,
        substance: event.substance
      };

      // Check if this is a system rejection message
      if (event.content.startsWith('<system>')) {
        msg.isSystemRejection = true;

        // Extract rejection reason (remove <system> tags)
        const match = event.content.match(/<system>(.*?)<\/system>/s);
        if (match) {
          msg.rejectionReason = match[1].trim();
        }

        // Mark the previous assistant message from this agent as failed
        for (let i = messages.length - 1; i >= 0; i--) {
          if (messages[i].agent === event.agent && messages[i].role === 'assistant') {
            messages[i].isFailed = true;
            break;
          }
        }
      }

      messages.push(msg);
    }
    // Assistant messages with tool_calls
    else if (event.role === 'assistant' && event.tool_calls) {
      // Attach tool results to each tool call
      const toolCallsWithResults = event.tool_calls.map(toolCall => {
        const result = toolResults.get(toolCall.id);
        const toolCallCopy = { ...toolCall };
        if (result) {
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

export function parseLog(text) {
  const lines = text.split('\n').filter(line => line.trim());
  const events = lines.map(line => JSON.parse(line));

  const state = {
    agents: {},
    messages: [],
    hooksByParent: new Map(),
    toolResults: new Map()
  };

  // Process all events using the same logic as incremental updates
  for (const event of events) {
    processEvent(event, state);
  }

  return { agents: state.agents, messages: state.messages };
}

/**
 * Deduplicate messages based on substance only
 */
export function deduplicateMessages(messages) {
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

    // For messages without substance, track by ID so other messages can reference them
    if (!msg.substance) {
      seenSubstance.add(msg.id);
    }

    result.push(msg);
  }

  return result;
}
