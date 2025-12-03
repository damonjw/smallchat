import { writable, derived } from 'svelte/store';

// Raw log data
export const logData = writable([]);

// Parsed agents: { agentId: { id, name, parent, children: [] } }
export const agents = writable({});

// All messages in chronological order
export const allMessages = writable([]);

// Currently active chat panels: [{ id, agentIds: [] }]
export const panels = writable([]);

// Derived: get the interlocutor (first agent with parent='user')
export const interlocutor = derived(agents, $agents => {
  return Object.values($agents).find(a => a.parent === 'user');
});

// Initialize first panel with interlocutor when it's loaded
interlocutor.subscribe(inter => {
  if (inter) {
    panels.update(p => {
      // Only auto-populate if there are no panels yet
      if (p.length === 0) {
        return [{ id: 0, agentIds: [inter.id] }];
      }
      return p;
    });
  }
});
