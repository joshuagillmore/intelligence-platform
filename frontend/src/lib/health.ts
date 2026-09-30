/**
 * Reading the backend's `/health` body.
 *
 * A 2xx is not "nominal" on its own: `/health` answers 200 with
 * `status: "degraded"` when Neo4j (or a configured Ollama) is unreachable, so
 * only `status === "ok"` counts as healthy. Anything else, including a body
 * with no status at all, is degraded.
 */
export type HealthLevel = 'checking' | 'ok' | 'degraded' | 'down';

export interface HealthReading {
  level: Exclude<HealthLevel, 'checking' | 'down'>;
  /** What is down, when the body says ("Neo4j down"); '' otherwise. */
  detail: string;
}

export function readHealth(data: unknown): HealthReading {
  const body = (data && typeof data === 'object' ? data : {}) as Record<string, unknown>;
  if (body.status === 'ok') return { level: 'ok', detail: '' };
  // Neo4j first: when it is down, ollama_connected may be false only because
  // Ollama is not configured, which the backend does not count as degraded.
  if (body.neo4j_connected === false) return { level: 'degraded', detail: 'Neo4j down' };
  if (body.ollama_connected === false) return { level: 'degraded', detail: 'Ollama down' };
  return { level: 'degraded', detail: '' };
}
