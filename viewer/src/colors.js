/**
 * Generate consistent colors for agents
 * Uses a pastel palette with similar brightness
 */

// High-quality hash function with better distribution
// Uses bit mixing techniques similar to MurmurHash
function hashString(str) {
  // Convert string to UTF-8 bytes
  const encoder = new TextEncoder();
  const data = encoder.encode(str);

  let h1 = 0xdeadbeef;
  let h2 = 0x41c6ce57;

  for (let i = 0; i < data.length; i++) {
    const byte = data[i];

    // Mix with different primes for each hash
    h1 = Math.imul(h1 ^ byte, 2654435761);
    h2 = Math.imul(h2 ^ byte, 1597334677);

    // Additional mixing with bit rotation
    h1 = (h1 << 13) | (h1 >>> 19);
    h2 = (h2 << 17) | (h2 >>> 15);
  }

  // Final avalanche mixing
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507);
  h1 = Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  h1 = (h1 ^ (h1 >>> 16)) >>> 0;

  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507);
  h2 = Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = (h2 ^ (h2 >>> 16)) >>> 0;

  // Combine both hashes for better distribution
  return (h1 + h2) >>> 0;
}

/**
 * Get pastel background color for agent badge
 */
export function getAgentBadgeColor(agentId) {
  const hash = hashString(agentId);
  const hue = hash % 360;

  // Pastel: high lightness (85%), low saturation (45%)
  return `hsl(${hue}, 45%, 85%)`;
}

/**
 * Get darker, more saturated color for agent name in text
 */
export function getAgentTextColor(agentId) {
  const hash = hashString(agentId);
  const hue = hash % 360;

  // Darker and more saturated: lower lightness (35%), higher saturation (60%)
  return `hsl(${hue}, 60%, 35%)`;
}

/**
 * Get border color for agent badge (slightly darker than background)
 */
export function getAgentBorderColor(agentId) {
  const hash = hashString(agentId);
  const hue = hash % 360;

  // Medium: lightness (70%), saturation (50%)
  return `hsl(${hue}, 50%, 70%)`;
}
