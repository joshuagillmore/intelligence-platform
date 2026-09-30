import { describe, it, expect } from 'vitest';
import { createSummaryStreamParser, type SummaryStreamEvent } from '@/lib/sse';

/**
 * The topic-summary stream sends every `data:` payload as a JSON string so
 * newlines inside the markdown survive the SSE framing; `[DONE]` ends it and
 * `{"error": "..."}` reports a failure. Network reads split events anywhere,
 * so the parser must buffer across reads and only act on complete events.
 */
function feed(chunks: string[]): SummaryStreamEvent[] {
  const parser = createSummaryStreamParser();
  const out: SummaryStreamEvent[] = [];
  for (const c of chunks) out.push(...parser.push(c));
  out.push(...parser.end());
  return out;
}

function text(events: SummaryStreamEvent[]): string {
  return events.map((e) => (e.type === 'text' ? e.text : '')).join('');
}

describe('createSummaryStreamParser', () => {
  it('keeps the newlines of a multi-line markdown summary', () => {
    const summary = '## Key Findings\n- APT29 staged infrastructure\n- Two domains share a registrant';
    const events = feed([`data: ${JSON.stringify(summary)}\n\n`, 'data: [DONE]\n\n']);
    expect(text(events)).toBe(summary);
    expect(events[events.length - 1]).toEqual({ type: 'done' });
  });

  it('reassembles events split across reads, including mid-JSON and mid-delimiter', () => {
    const a = JSON.stringify('## Key actors\n');
    const b = JSON.stringify('- APT29\n- Cozy Bear');
    const wire = `data: ${a}\n\ndata: ${b}\n\ndata: [DONE]\n\n`;
    // Split at every possible point and at a few awkward pairs.
    for (let i = 1; i < wire.length; i++) {
      const events = feed([wire.slice(0, i), wire.slice(i)]);
      expect(text(events)).toBe('## Key actors\n- APT29\n- Cozy Bear');
    }
    const odd = feed([wire.slice(0, 7), wire.slice(7, 21), wire.slice(21, 22), wire.slice(22)]);
    expect(text(odd)).toBe('## Key actors\n- APT29\n- Cozy Bear');
  });

  it('handles several events in one read', () => {
    const wire = ['one', ' two', ' three'].map((t) => `data: ${JSON.stringify(t)}\n\n`).join('');
    expect(text(feed([wire]))).toBe('one two three');
  });

  it('accepts CRLF framing', () => {
    const wire = `data: ${JSON.stringify('line 1\nline 2')}\r\n\r\ndata: [DONE]\r\n\r\n`;
    expect(text(feed([wire]))).toBe('line 1\nline 2');
  });

  it('stops at [DONE] and ignores anything after it', () => {
    const wire = `data: ${JSON.stringify('kept')}\n\ndata: [DONE]\n\ndata: ${JSON.stringify('dropped')}\n\n`;
    const events = feed([wire]);
    expect(text(events)).toBe('kept');
  });

  it('reports an error event with its message', () => {
    const events = feed([`data: ${JSON.stringify({ error: 'Summary generation failed' })}\n\n`]);
    expect(events).toEqual([{ type: 'error', message: 'Summary generation failed' }]);
  });

  it('treats a payload that is not JSON as an error, not as summary text', () => {
    const events = feed(['data: ## Key Findings\n\n']);
    expect(events).toHaveLength(1);
    expect(events[0].type).toBe('error');
  });

  it('flushes a final event that arrived without a trailing blank line', () => {
    const events = feed([`data: ${JSON.stringify('tail')}`]);
    expect(text(events)).toBe('tail');
  });

  it('ignores comments and non-data fields', () => {
    const wire = `: keep-alive\n\nevent: message\ndata: ${JSON.stringify('x')}\n\n`;
    expect(text(feed([wire]))).toBe('x');
  });
});
