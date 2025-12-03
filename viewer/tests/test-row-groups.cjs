#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

// Copy of parseLog function
function parseLog(text) {
  const lines = text.split('\n').filter(line => line.trim());
  const events = lines.map(line => JSON.parse(line));

  const agents = {};
  const messages = [];

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

  for (const agent of Object.values(agents)) {
    if (agent.parent && agent.parent !== 'user' && agents[agent.parent]) {
      agents[agent.parent].children.push(agent.id);
    }
  }

  for (const event of events) {
    if (event.event_type === 'transcript_entry') {
      if (event.role === 'system' && agents[event.agent]) {
        agents[event.agent].systemPrompts.push(event.content);
      }
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

// Copy of deduplicateMessages
function deduplicateMessages(messages) {
  const seen = new Set();
  const seenSubstance = new Set();
  const result = [];

  for (const msg of messages) {
    if (msg.substance) {
      if (seenSubstance.has(msg.substance)) {
        continue;
      }
      seenSubstance.add(msg.substance);
    }

    const contentKey = `${msg.role}:${msg.content}`;
    if (seen.has(contentKey)) {
      continue;
    }

    seen.add(contentKey);
    if (!msg.substance) {
      seenSubstance.add(msg.id);
    }

    result.push(msg);
  }

  return result;
}

// Copy of getPerPanelMessages
function getPerPanelMessages(allMessages, panels) {
  const panelMessages = new Map();

  for (const panel of panels) {
    const panelMsgs = allMessages.filter(msg => panel.agentIds.includes(msg.agent));
    const dedupedMsgs = deduplicateMessages(panelMsgs);
    panelMessages.set(panel.id, new Set(dedupedMsgs.map(m => m.id)));
  }

  return panelMessages;
}

// Copy of createRowGroups
function createRowGroups(allMessages, panelMessages, panels) {
  const rowGroups = [];
  const substanceToRow = new Map();
  const messageIdToRow = new Map();
  const processedMessageIds = new Set();

  for (const msg of allMessages) {
    if (processedMessageIds.has(msg.id)) continue;

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
      if (substanceToRow.has(msg.substance)) {
        rowIndex = substanceToRow.get(msg.substance);
        rowGroups[rowIndex].messages.push(msg);
      }
      else if (messageIdToRow.has(msg.substance)) {
        rowIndex = messageIdToRow.get(msg.substance);
        rowGroups[rowIndex].messages.push(msg);
        substanceToRow.set(msg.substance, rowIndex);
      }
      else {
        rowIndex = rowGroups.length;
        substanceToRow.set(msg.substance, rowIndex);
        rowGroups.push({
          substance: msg.substance,
          messages: [msg]
        });
      }
    } else {
      rowIndex = rowGroups.length;
      rowGroups.push({
        substance: null,
        messages: [msg]
      });
      messageIdToRow.set(msg.id, rowIndex);
    }

    processedMessageIds.add(msg.id);
  }

  return rowGroups;
}

// Main test
const logFile = path.join(__dirname, '..', '..', '.chats', 'chat0.jsonl');
const logContent = fs.readFileSync(logFile, 'utf-8');

const { agents, messages } = parseLog(logContent);

// Create two panels: one for Andrew, one for Bea
const panels = [
  { id: 1, agentIds: ['andrew'] },
  { id: 2, agentIds: ['bea'] }
];

const panelMessages = getPerPanelMessages(messages, panels);
const rowGroups = createRowGroups(messages, panelMessages, panels);

console.log('=== Row Groups ===\n');
for (let i = 0; i < rowGroups.length; i++) {
  const group = rowGroups[i];
  console.log(`Row ${i + 1}:`);
  console.log(`  Substance: ${group.substance || 'none'}`);
  console.log(`  Messages in this row:`);
  for (const msg of group.messages) {
    console.log(`    - Message ${msg.id} (${msg.agent}): ${msg.content.substring(0, 60)}...`);
  }
  console.log();
}

console.log(`\n=== Total rows: ${rowGroups.length} ===`);

// Check for substance 32
const row32 = rowGroups.find(g => g.substance === '32');
if (row32) {
  console.log('\n=== Row with substance 32 ===');
  console.log(`Contains ${row32.messages.length} messages:`);
  for (const msg of row32.messages) {
    console.log(`  - Message ${msg.id} (${msg.agent})`);
  }
}
