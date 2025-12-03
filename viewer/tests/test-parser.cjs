#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

// Copy of parseLog function from logParser.js
function parseLog(text) {
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

  // Third pass: extract messages and system prompts
  for (const event of events) {
    if (event.event_type === 'transcript_entry') {
      // Extract system prompts
      if (event.role === 'system' && agents[event.agent]) {
        agents[event.agent].systemPrompts.push(event.content);
      }
      // Only show user messages (inputs) and assistant messages without tool_calls (utterances)
      else if (event.role === 'user') {
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

// Copy of deduplicateMessages function from logParser.js
function deduplicateMessages(messages, debug = false) {
  const seen = new Set();
  const seenSubstance = new Set();
  const result = [];

  for (const msg of messages) {
    let skipReason = null;

    // Check substance-based deduplication
    if (msg.substance) {
      if (seenSubstance.has(msg.substance)) {
        skipReason = `substance ${msg.substance} already seen`;
      } else {
        seenSubstance.add(msg.substance);
      }
    }

    // Check content-based deduplication
    if (!skipReason) {
      const contentKey = `${msg.role}:${msg.content}`;
      if (seen.has(contentKey)) {
        skipReason = `content already seen`;
      } else {
        seen.add(contentKey);
        if (!msg.substance) {
          seenSubstance.add(msg.id);
        }
      }
    }

    if (skipReason) {
      if (debug && msg.agent === 'bea') {
        console.log(`  [SKIP] Message ${msg.id} (${msg.agent}): ${skipReason}`);
      }
      continue;
    }

    if (debug && msg.agent === 'bea') {
      console.log(`  [KEEP] Message ${msg.id} (${msg.agent}): substance=${msg.substance}`);
    }

    result.push(msg);
  }

  return result;
}

// Main test script
const logFile = path.join(__dirname, '..', '..', '.chats', 'chat0.jsonl');
const logContent = fs.readFileSync(logFile, 'utf-8');

console.log('=== Parsing log file ===\n');
const { agents, messages } = parseLog(logContent);

console.log('Agents found:');
for (const [id, agent] of Object.entries(agents)) {
  console.log(`  - ${id}: ${agent.name}`);
}
console.log();

console.log(`Total messages before deduplication: ${messages.length}`);
console.log();

console.log('Messages for Bea BEFORE deduplication:');
const beaMessagesBefore = messages.filter(m => m.agent === 'bea');
for (const msg of beaMessagesBefore) {
  console.log(`  Message ${msg.id}: ${msg.role}, substance=${msg.substance}`);
  console.log(`    Content: ${msg.content.substring(0, 80)}...`);
}
console.log();

console.log('All messages in processing order:');
for (const msg of messages) {
  console.log(`  Message ${msg.id} (${msg.agent}/${msg.role}): substance=${msg.substance || 'none'}`);
}
console.log();

// Simulate per-panel deduplication for Bea's panel
console.log('=== Per-panel deduplication for Bea panel ===');
const beaPanel = messages.filter(m => m.agent === 'bea');
console.log(`Messages in Bea panel BEFORE deduplication: ${beaPanel.length}`);
const beaPanelDeduped = deduplicateMessages(beaPanel, true);
console.log();
console.log(`Messages in Bea panel AFTER deduplication: ${beaPanelDeduped.length}`);
console.log();

console.log('Bea panel will show:');
for (const msg of beaPanelDeduped) {
  console.log(`  Message ${msg.id}: ${msg.role}, substance=${msg.substance || 'none'}`);
  console.log(`    Content: ${msg.content.substring(0, 80)}...`);
}
console.log();

// Check if message 34 is included
const hasMsg34 = beaPanelDeduped.some(m => m.id === '34');
console.log(`=== Message 34 is ${hasMsg34 ? 'INCLUDED' : 'MISSING'} in Bea panel ===`);
