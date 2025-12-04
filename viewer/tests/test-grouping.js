import { parseLog } from './src/logParser.js';
import { readFileSync } from 'fs';

// Read and parse chat1.jsonl
const logText = readFileSync('../.chats/chat1.jsonl', 'utf-8');
const { agents, messages } = parseLog(logText);

console.log('=== Testing Tool Message Grouping ===\n');

// Find Jack's agent id
const jackAgent = Object.values(agents).find(a => a.name === 'Jack');
console.log('Jack agent id:', jackAgent?.id);

// Filter messages for Jack
const jackMessages = messages.filter(m => m.agent === jackAgent?.id);

console.log('\nJack\'s messages:');
jackMessages.forEach((msg, idx) => {
  console.log(`${idx}. Message ${msg.id}: role=${msg.role}, substance=${msg.substance || 'none'}`);
  if (msg.role === 'assistant_tool_use') {
    console.log(`   Tool calls: ${msg.tool_calls?.length || 0}`);
  }
  if (msg.content) {
    console.log(`   Content preview: ${msg.content.substring(0, 50)}...`);
  }
});

// Check specifically for messages 41 and 46
console.log('\n=== Messages 41 and 46 ===');
const msg41 = messages.find(m => m.id === '41');
const msg46 = messages.find(m => m.id === '46');

console.log('Message 41:', msg41 ? {
  id: msg41.id,
  agent: msg41.agent,
  role: msg41.role,
  substance: msg41.substance,
  tool_calls: msg41.tool_calls?.length
} : 'NOT FOUND');

console.log('Message 46:', msg46 ? {
  id: msg46.id,
  agent: msg46.agent,
  role: msg46.role,
  substance: msg46.substance,
  tool_calls: msg46.tool_calls?.length
} : 'NOT FOUND');

// Check if they're consecutive in Jack's filtered list
const msg41Index = jackMessages.findIndex(m => m.id === '41');
const msg46Index = jackMessages.findIndex(m => m.id === '46');

console.log('\nIn Jack\'s filtered message list:');
console.log('  Message 41 is at index:', msg41Index);
console.log('  Message 46 is at index:', msg46Index);
console.log('  Messages between them:', msg46Index - msg41Index - 1);

if (msg46Index - msg41Index === 1) {
  console.log('  ✓ Messages are consecutive - should be grouped');
} else {
  console.log('  ✗ Messages are NOT consecutive - grouping will fail');
  console.log('  Messages in between:');
  for (let i = msg41Index + 1; i < msg46Index; i++) {
    const msg = jackMessages[i];
    console.log(`    - Message ${msg.id}: ${msg.role}`);
  }
}

// Test the grouping function
console.log('\n=== Testing groupToolMessages function ===');

function groupToolMessages(messages) {
  const result = [];
  let i = 0;

  while (i < messages.length) {
    const msg = messages[i];

    if (msg.role === 'assistant_tool_use') {
      const toolGroup = [msg];
      let j = i + 1;

      while (j < messages.length &&
             messages[j].role === 'assistant_tool_use' &&
             messages[j].agent === msg.agent) {
        toolGroup.push(messages[j]);
        j++;
      }

      result.push({
        type: 'tool_group',
        agent: msg.agent,
        messages: toolGroup
      });

      i = j;
    } else {
      result.push({
        type: 'message',
        message: msg
      });
      i++;
    }
  }

  return result;
}

// Test with a subset around messages 41 and 46
const testMessages = jackMessages.slice(
  Math.max(0, msg41Index - 1),
  Math.min(jackMessages.length, msg46Index + 2)
);

console.log('Testing with messages:', testMessages.map(m => `${m.id}(${m.role})`).join(', '));
const grouped = groupToolMessages(testMessages);
console.log('Grouped result:');
grouped.forEach((item, idx) => {
  if (item.type === 'tool_group') {
    console.log(`  ${idx}. TOOL GROUP: ${item.messages.map(m => m.id).join(', ')}`);
  } else {
    console.log(`  ${idx}. MESSAGE: ${item.message.id} (${item.message.role})`);
  }
});

// Test row grouping logic
console.log('\n=== Testing createRowGroups (simulated) ===');

function createRowGroups(allMessages) {
  const rowGroups = [];
  const messageIdToRow = new Map();
  const processedMessageIds = new Set();

  for (const msg of allMessages) {
    if (processedMessageIds.has(msg.id)) continue;

    let rowIndex;

    if (msg.substance) {
      // Has substance - handle normally (simplified for test)
      rowIndex = rowGroups.length;
      rowGroups.push({
        substance: msg.substance,
        messages: [msg]
      });
    } else {
      // No substance - check if this should be grouped with previous tool_use messages
      if (msg.role === 'assistant_tool_use' && rowGroups.length > 0) {
        const lastRow = rowGroups[rowGroups.length - 1];
        const lastMsg = lastRow.messages[lastRow.messages.length - 1];

        if (lastMsg.role === 'assistant_tool_use' && lastMsg.agent === msg.agent) {
          // Add to the existing row
          rowIndex = rowGroups.length - 1;
          rowGroups[rowIndex].messages.push(msg);
        } else {
          // Create new row
          rowIndex = rowGroups.length;
          rowGroups.push({
            substance: null,
            messages: [msg]
          });
        }
      } else {
        // Create new row
        rowIndex = rowGroups.length;
        rowGroups.push({
          substance: null,
          messages: [msg]
        });
      }
      messageIdToRow.set(msg.id, rowIndex);
    }

    processedMessageIds.add(msg.id);
  }

  return rowGroups;
}

const rowGroups = createRowGroups(testMessages);
console.log('Row groups created:');
rowGroups.forEach((row, idx) => {
  console.log(`  Row ${idx} (substance: ${row.substance || 'none'}):`,
    row.messages.map(m => `${m.id}(${m.role})`).join(', '));
});

console.log('\n=== Result ===');
const row41 = rowGroups.findIndex(r => r.messages.some(m => m.id === '41'));
const row46 = rowGroups.findIndex(r => r.messages.some(m => m.id === '46'));

if (row41 === row46) {
  console.log('✓ SUCCESS: Messages 41 and 46 are in the same row (row', row41 + ')');
  console.log('  Messages in that row:', rowGroups[row41].messages.map(m => m.id).join(', '));
} else {
  console.log('✗ FAILURE: Messages 41 and 46 are in different rows');
  console.log('  Message 41 is in row', row41);
  console.log('  Message 46 is in row', row46);
}
