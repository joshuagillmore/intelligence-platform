/**
 * Parser for the topic-summary server-sent-event stream.
 *
 * Wire format (the backend contract): every `data:` payload is a JSON value.
 * A JSON string is summary text to append; `{"error": "..."}` is a failure;
 * the literal `[DONE]` ends the stream. Events are separated by a blank line.
 *
 * Network reads split the stream anywhere (inside the JSON, inside the blank
 * line), so the parser buffers and only acts on complete events. JSON-encoding
 * each payload is what lets newlines inside the markdown survive SSE framing,
 * so a payload that is not JSON is reported as an error rather than appended
 * as text.
 */
export type SummaryStreamEvent =
  | { type: 'text'; text: string }
  | { type: 'error'; message: string }
  | { type: 'done' };

export interface SummaryStreamParser {
  /** Feed one decoded read; returns the events it completed. */
  push(chunk: string): SummaryStreamEvent[];
  /** Call once the body ends; flushes a final event with no trailing blank line. */
  end(): SummaryStreamEvent[];
}

const EVENT_BOUNDARY = /\r?\n\r?\n/;

function parseEvent(block: string): SummaryStreamEvent | null {
  const dataLines: string[] = [];
  for (const rawLine of block.split(/\r?\n/)) {
    if (!rawLine.startsWith('data:')) continue; // comments, event:, id:, retry:
    const value = rawLine.slice(5);
    dataLines.push(value.startsWith(' ') ? value.slice(1) : value);
  }
  if (dataLines.length === 0) return null;
  const payload = dataLines.join('\n');
  if (payload === '[DONE]') return { type: 'done' };

  let parsed: unknown;
  try {
    parsed = JSON.parse(payload);
  } catch {
    return { type: 'error', message: 'The summary stream sent a payload that is not JSON.' };
  }
  if (typeof parsed === 'string') return { type: 'text', text: parsed };
  if (parsed && typeof parsed === 'object' && 'error' in parsed) {
    const message = (parsed as { error: unknown }).error;
    return { type: 'error', message: typeof message === 'string' && message ? message : 'Summary generation failed' };
  }
  return { type: 'error', message: 'The summary stream sent an unexpected payload.' };
}

export function createSummaryStreamParser(): SummaryStreamParser {
  let buffer = '';
  let finished = false;

  const drain = (blocks: string[]): SummaryStreamEvent[] => {
    const events: SummaryStreamEvent[] = [];
    for (const block of blocks) {
      if (finished) break;
      const event = parseEvent(block);
      if (!event) continue;
      events.push(event);
      if (event.type === 'done' || event.type === 'error') finished = true;
    }
    return events;
  };

  return {
    push(chunk: string) {
      if (finished) return [];
      buffer += chunk;
      const parts = buffer.split(EVENT_BOUNDARY);
      // The last part is incomplete until its blank line arrives. A trailing
      // "\r\n\r" could still become a boundary, so it stays buffered too.
      buffer = parts.pop() ?? '';
      return drain(parts);
    },
    end() {
      if (finished) return [];
      const rest = buffer;
      buffer = '';
      return rest.trim() ? drain([rest]) : [];
    },
  };
}
