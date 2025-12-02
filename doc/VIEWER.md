# Multi-Agent Event Log Viewer

## Current Architecture

The viewer is a single-page Svelte application that compiles to a standalone HTML file (46.66 kB, gzip: 17.88 kB).

### Component Structure
- **App.svelte**: Main component with file drag-and-drop
- **AgentHierarchy.svelte**: Displays agent tree
- **AgentNode.svelte**: Recursive tree node with inline single-child chains
- **ChatPanels.svelte**: Unified scroll container with panel headers and message grid
- **Message.svelte**: Individual message display

### State Management (stores.js)
- `agents`: Map of agent_id → {id, name, parent, children[]}
- `allMessages`: Array of all parsed messages
- `panels`: Array of {id, agentIds[]} for each chat panel
- `interlocutor`: Derived store for the top-level agent

### Parsing (logParser.js)
- `parseLog(text)`: Parses entire .jsonl file, builds agent tree, extracts messages
- `deduplicateMessages(messages)`: Removes duplicates based on substance and content
- Only includes:
  - User messages (inputs): `role === 'user'`
  - Assistant messages without tool calls (utterances): `role === 'assistant' && !tool_calls`

### Current Behavior
1. User drags .jsonl file onto drop zone
2. File is read entirely as text via `file.text()`
3. Entire log is parsed in one pass
4. Agents and messages populate stores
5. UI renders based on store state

## Goal: Live File Updates

Enable the viewer to show a log file that is actively being written, with automatic updates as new entries are added.

## Implementation Plan: Auto-Polling with File Handle

### Overview
Use the File System Access API to maintain access to the file, poll periodically for changes, incrementally parse new content, and update stores.

### Technical Approach

#### 1. File System Access API
After user drops file, request a FileHandle:
```javascript
const fileHandle = await file.handle; // Available on File objects from drag-and-drop
```

Store this handle to read the file repeatedly without user re-selection.

**Browser Support:** Chrome 86+, Edge 86+, Safari 15.2+ (well supported in modern browsers)

#### 2. Polling Strategy
- Poll every 2-3 seconds when in "Live mode"
- Track last read position (byte offset or line count)
- Read only new content since last poll
- Stop polling when Live mode is disabled or file is unloaded

#### 3. Incremental Parsing
Current `parseLog(text)` parses the entire file. Need to modify to support incremental parsing:

**New function:**
```javascript
parseLogIncremental(newLines, existingAgents, existingMessages)
```

This function:
- Takes only the NEW lines that have been added
- Takes existing agents and messages maps
- Parses new events
- Updates agent tree (adds new agents, updates children arrays)
- Appends new messages
- Returns updated agents and messages

**Key insight:** Events are append-only. Agents are only created (never modified/deleted). Messages are only added (never modified/deleted). This makes incremental updates straightforward.

#### 4. Store Updates
Modify stores to support incremental updates:
```javascript
// Instead of:
agents.set(parsedAgents);
allMessages.set(dedupedMessages);

// Use:
agents.update(existing => ({ ...existing, ...newAgents }));
allMessages.update(existing => [...existing, ...newMessages]);
```

Need to track which message IDs have been seen for deduplication.

### Implementation Steps

#### Step 1: Refactor File Handling (App.svelte)
- Store the FileHandle after file drop
- Add "Live mode" toggle button (only appears after file is loaded)
- Add polling interval management

**Changes:**
```javascript
let fileHandle = null;
let liveMode = false;
let pollingInterval = null;
let lastReadLineCount = 0;

async function handleDrop(e) {
  // ... existing code ...

  // Get file handle for future reads
  const file = files[0];
  fileHandle = await file.handle || null;

  // Initial full parse
  const text = await file.text();
  lastReadLineCount = text.split('\n').length;

  const { agents: parsedAgents, messages } = parseLog(text);
  // ... rest of existing code ...
}

function toggleLiveMode() {
  liveMode = !liveMode;
  if (liveMode && fileHandle) {
    startPolling();
  } else {
    stopPolling();
  }
}

function startPolling() {
  pollingInterval = setInterval(async () => {
    await pollForUpdates();
  }, 2500); // Poll every 2.5 seconds
}

function stopPolling() {
  if (pollingInterval) {
    clearInterval(pollingInterval);
    pollingInterval = null;
  }
}

async function pollForUpdates() {
  if (!fileHandle) return;

  try {
    const file = await fileHandle.getFile();
    const text = await file.text();
    const lines = text.split('\n');

    // Get only new lines since last read
    const newLines = lines.slice(lastReadLineCount);
    if (newLines.length === 0) return;

    lastReadLineCount = lines.length;

    // Incremental parse
    const { newAgents, newMessages } = parseLogIncremental(
      newLines,
      $agents,
      $allMessages
    );

    // Update stores
    agents.update(existing => ({ ...existing, ...newAgents }));

    const dedupedNewMessages = deduplicateMessages(
      [...$allMessages, ...newMessages]
    );
    allMessages.set(dedupedNewMessages);

  } catch (error) {
    console.error('Error polling file:', error);
    // Could add error UI here
  }
}
```

#### Step 2: Implement Incremental Parser (logParser.js)

**New function:**
```javascript
export function parseLogIncremental(newLines, existingAgents, existingMessages) {
  const lines = newLines.filter(line => line.trim());
  const events = lines.map(line => JSON.parse(line));

  const newAgents = {};
  const newMessages = [];

  // Process new events
  for (const event of events) {
    if (event.event_type === 'agent_created') {
      // Create new agent
      const agent = {
        id: event.agent,
        name: event.name,
        parent: event.parent,
        children: []
      };
      newAgents[event.agent] = agent;

      // Update parent's children array
      if (event.parent && event.parent !== 'user') {
        const parent = existingAgents[event.parent] || newAgents[event.parent];
        if (parent && !parent.children.includes(event.agent)) {
          parent.children.push(event.agent);
        }
      }
    }
    else if (event.event_type === 'transcript_entry') {
      // Extract message (same logic as current parseLog)
      if (event.role === 'user') {
        newMessages.push({
          id: event.message_id,
          agent: event.agent,
          role: 'user',
          content: event.content,
          substance: event.substance
        });
      } else if (event.role === 'assistant' && !event.tool_calls) {
        newMessages.push({
          id: event.message_id,
          agent: event.agent,
          role: 'assistant',
          content: event.content,
          substance: event.substance
        });
      }
    }
  }

  return { newAgents, newMessages };
}
```

#### Step 3: Update Deduplication Logic (logParser.js)

Current `deduplicateMessages` assumes it's processing the entire message list. For incremental updates, we need to track which substance IDs and content we've already seen.

**Option A:** Re-run deduplication on the entire message list each time (simpler, slightly less efficient)

**Option B:** Maintain a persistent Set of seen substance IDs and content keys in a store (more complex, more efficient)

**Recommendation:** Start with Option A for simplicity. The message list won't be huge, and re-deduplicating is fast.

#### Step 4: Add UI Controls (App.svelte)

Add a toggle button for Live mode in the viewer:

```svelte
{:else}
  <div class="viewer">
    <div class="viewer-controls">
      <label>
        <input type="checkbox" bind:checked={liveMode} on:change={toggleLiveMode} />
        Live mode {liveMode ? '(polling...)' : ''}
      </label>
      {#if !fileHandle}
        <span class="warning">Live mode not available (browser limitation)</span>
      {/if}
    </div>
    <div class="hierarchy-section">
      <AgentHierarchy />
    </div>
    <!-- ... rest of viewer ... -->
  </div>
{/if}
```

Style the controls to be unobtrusive (small, top-right corner).

#### Step 5: Handle Edge Cases

**File Handle Not Available:**
- File System Access API may not provide handles in all contexts
- Fallback: Disable Live mode, show message to user

**File Deleted/Moved:**
- `fileHandle.getFile()` will throw
- Catch error, disable Live mode, show message

**Parse Errors:**
- New lines may be malformed JSON
- Catch errors, log them, continue polling
- Could show parse error count in UI

**Agent Tree Consistency:**
- If parent agent hasn't been created yet when child is created, handle gracefully
- May need to queue orphaned agents and resolve later

#### Step 6: Performance Considerations

**Polling Frequency:**
- 2-3 seconds is reasonable for most use cases
- Could make this configurable

**Large Files:**
- Reading entire file on each poll is acceptable for files up to ~10MB
- For larger files, could use streaming or seek to last position (more complex)

**Deduplication Cost:**
- Re-running deduplication on entire message list is O(n) where n = total messages
- For 1000s of messages, this is negligible
- For 10,000s of messages, consider Option B (persistent seen Sets)

### Future Enhancements

**Auto-scroll:**
- When new messages arrive, auto-scroll to bottom of panels
- Add "pause auto-scroll" when user manually scrolls up

**Visual Indicators:**
- Highlight newly added messages (fade in animation)
- Show polling status indicator (pulsing dot)
- Show last update timestamp

**Smarter Polling:**
- Use exponential backoff if file hasn't changed
- Use file size check before reading full content (optimization)

**Error Recovery:**
- If polling fails, retry with backoff
- Allow user to manually trigger refresh

### Testing Plan

1. **Basic Live Updates:**
   - Load file, enable Live mode
   - Append new log entries to file
   - Verify viewer updates within polling interval

2. **Agent Creation:**
   - Add new agent_created events
   - Verify hierarchy updates correctly
   - Verify parent-child relationships update

3. **Message Deduplication:**
   - Add messages with substance fields
   - Verify duplicates are still filtered out

4. **Error Handling:**
   - Delete file while polling
   - Add malformed JSON lines
   - Revoke file permissions

5. **Performance:**
   - Load large file (1000+ messages)
   - Enable Live mode
   - Verify polling remains smooth

## Technical Notes

### File System Access API Reference

```javascript
// Get FileHandle from drop event
const file = e.dataTransfer.files[0];
const fileHandle = await file.handle;

// Read file later
if (fileHandle) {
  const file = await fileHandle.getFile();
  const text = await file.text();
}
```

**Permissions:** User grants access by dropping the file. Handle persists for the session.

**Browser Compatibility:**
- Chrome/Edge: Full support
- Firefox: Partial support (may not have .handle on File objects)
- Safari: Recent support

**Fallback:** If `.handle` is undefined, disable Live mode with message: "Live mode not supported in this browser"

### Store Update Patterns

**Adding new agents:**
```javascript
agents.update(existing => ({ ...existing, ...newAgents }));
```

**Updating agent children:**
```javascript
agents.update(existing => {
  const updated = { ...existing };
  updated[parentId] = {
    ...updated[parentId],
    children: [...updated[parentId].children, childId]
  };
  return updated;
});
```

**Adding new messages:**
```javascript
allMessages.update(existing => {
  const combined = [...existing, ...newMessages];
  return deduplicateMessages(combined);
});
```

## Summary

**Effort Estimate:** 2-3 hours for core implementation, 1 hour for polish and testing

**Risk Level:** Low-medium
- File System Access API is well-supported
- Incremental parsing is straightforward (append-only events)
- Main risk is edge cases (file access errors, malformed data)

**User Experience:**
- Drop file as usual
- Toggle "Live mode" checkbox
- Viewer updates automatically every 2-3 seconds
- Can toggle off to pause updates

**Maintains Design Goals:**
- Single HTML file (no server required)
- Simple user interaction
- Works offline
- Clean, focused UI
