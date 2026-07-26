import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TemporalHistogram, { HistogramData } from '@/components/TemporalHistogram';

/**
 * The brush filters the network graph by when things happened. Its honesty
 * matters more than its looks: a histogram that hides how much of the corpus is
 * undated, or that silently empties the graph, misleads the analyst reading it.
 */

const DATA: HistogramData = {
  bucket: 'month',
  bins: [
    { key: '2025-01', count: 1, by_type: { Event: 1 } },
    { key: '2026-03', count: 4, by_type: { Event: 4 } },
    { key: '2026-04', count: 2, by_type: { Event: 2 } },
  ],
  dated: 7,
  undated: 93,
  earliest: '2025-01-01T00:00:00+00:00',
  latest: '2026-04-30T00:00:00+00:00',
};

function setup(overrides: Partial<React.ComponentProps<typeof TemporalHistogram>> = {}) {
  const onChange = vi.fn();
  const onHideUndatedChange = vi.fn();
  const onBucketChange = vi.fn();
  render(
    <TemporalHistogram
      data={DATA}
      value={[null, null]}
      onChange={onChange}
      hideUndated={false}
      onHideUndatedChange={onHideUndatedChange}
      onBucketChange={onBucketChange}
      {...overrides}
    />,
  );
  return { onChange, onHideUndatedChange, onBucketChange };
}

describe('TemporalHistogram', () => {
  it('reports how much of the corpus is undated', () => {
    // Without this the analyst reads a sparse histogram as a quiet period
    // rather than as a corpus that mostly carries no dates.
    setup();
    expect(screen.getByText(/7 dated/)).toBeInTheDocument();
    expect(screen.getByText(/93 undated/)).toBeInTheDocument();
  });

  it('says so plainly when nothing is dated, rather than drawing an empty chart', () => {
    render(
      <TemporalHistogram
        data={{ ...DATA, bins: [], dated: 0, undated: 380 }}
        value={[null, null]}
        onChange={vi.fn()}
        hideUndated={false}
        onHideUndatedChange={vi.fn()}
      />,
    );
    expect(screen.getByText(/No dated events in this project/)).toBeInTheDocument();
    expect(screen.getByText(/380 entities, none carrying a date/)).toBeInTheDocument();
  });

  it('labels bins by the precision available, not as false exact days', () => {
    setup();
    // Month-bucketed data reads "Mar 2026", never "1 Mar 2026".
    expect(screen.getByLabelText(/Mar 2026, 4 events/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/1 Mar 2026/)).not.toBeInTheDocument();
  });

  it('selects a single bucket on click', async () => {
    const { onChange } = setup();
    await userEvent.click(screen.getByLabelText(/Mar 2026, 4 events/));
    expect(onChange).toHaveBeenCalledWith(['2026-03', '2026-03']);
  });

  it('shows the selected range and offers a clear', async () => {
    const { onChange } = setup({ value: ['2026-03', '2026-04'] });
    expect(screen.getByText('Mar 2026 – Apr 2026')).toBeInTheDocument();
    await userEvent.click(screen.getByTitle('Clear the time filter'));
    expect(onChange).toHaveBeenCalledWith([null, null]);
  });

  it('only offers "hide undated" while a range is selected', () => {
    const { unmount } = render(
      <TemporalHistogram
        data={DATA} value={[null, null]} onChange={vi.fn()}
        hideUndated={false} onHideUndatedChange={vi.fn()}
      />,
    );
    expect(screen.queryByLabelText(/Hide undated/i)).not.toBeInTheDocument();
    unmount();

    setup({ value: ['2026-03', '2026-04'] });
    expect(screen.getByText(/Hide undated/i)).toBeInTheDocument();
  });

  it('lets the analyst change bucket size', async () => {
    const { onBucketChange } = setup();
    await userEvent.click(screen.getByTitle('Bucket by year'));
    expect(onBucketChange).toHaveBeenCalledWith('year');
  });

  it('renders a loading state rather than an empty chart', () => {
    render(
      <TemporalHistogram
        data={null} loading value={[null, null]} onChange={vi.fn()}
        hideUndated={false} onHideUndatedChange={vi.fn()}
      />,
    );
    expect(screen.getByText(/Loading event dates/)).toBeInTheDocument();
  });
});

describe('range membership', () => {
  /**
   * The page filters nodes by comparing an ISO prefix against the bin key.
   * ISO dates sort lexicographically, so this needs no date parsing — but it
   * only holds if the prefix length matches the key length.
   */
  const inRange = (dt: string, start: string, end: string) => {
    const key = dt.slice(0, start.length);
    return key >= start && key <= end;
  };

  it('matches a day-precision date inside a month range', () => {
    expect(inRange('2026-03-12T00:00:00+00:00', '2026-03', '2026-04')).toBe(true);
  });

  it('excludes dates outside the range', () => {
    expect(inRange('2025-01-01T00:00:00+00:00', '2026-03', '2026-04')).toBe(false);
    expect(inRange('2026-05-01T00:00:00+00:00', '2026-03', '2026-04')).toBe(false);
  });

  it('works at year bucketing', () => {
    expect(inRange('2026-03-12T00:00:00+00:00', '2025', '2026')).toBe(true);
    expect(inRange('2024-12-31T00:00:00+00:00', '2025', '2026')).toBe(false);
  });

  it('includes the boundary buckets', () => {
    expect(inRange('2026-03-01T00:00:00+00:00', '2026-03', '2026-04')).toBe(true);
    expect(inRange('2026-04-30T00:00:00+00:00', '2026-03', '2026-04')).toBe(true);
  });
});
