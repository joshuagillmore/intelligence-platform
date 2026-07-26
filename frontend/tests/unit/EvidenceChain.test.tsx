import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import EvidenceChain, { probabilityLabel } from '@/components/EvidenceChain';

const base = {
  rel_type: 'USES',
  source_name: 'APT-Nebula',
  target_name: '45.83.12.7',
  confidence: 0.7,
  evidence: 'APT-Nebula used C2 server 45.83.12.7 to target TenneT.',
  corroboration_count: 1,
  corroboration_agreement: 'AGREE',
};

describe('probabilityLabel', () => {
  it('maps confidence onto IC-style wording', () => {
    expect(probabilityLabel(0.95)).toBe('Almost certain');
    expect(probabilityLabel(0.8)).toBe('Highly likely');
    expect(probabilityLabel(0.7)).toBe('Likely');
    expect(probabilityLabel(0.5)).toBe('Roughly even chance');
    expect(probabilityLabel(0.3)).toBe('Unlikely');
    expect(probabilityLabel(0.1)).toBe('Remote');
  });
});

describe('EvidenceChain', () => {
  it('renders the claim, its confidence and the verbatim basis', () => {
    render(<EvidenceChain relationship={base} />);
    // The entity appears twice by design: once as the claim, once highlighted
    // inside the excerpt that supports it.
    expect(screen.getAllByText('APT-Nebula').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('USES')).toBeInTheDocument();
    expect(screen.getByText('Likely')).toBeInTheDocument();
    expect(screen.getByText('70%')).toBeInTheDocument();
    expect(screen.getByText(/used C2 server/)).toBeInTheDocument();
  });

  it('highlights the claim entities inside the excerpt', () => {
    const { container } = render(<EvidenceChain relationship={base} />);
    const marks = Array.from(container.querySelectorAll('mark')).map(m => m.textContent);
    expect(marks).toContain('APT-Nebula');
    expect(marks).toContain('45.83.12.7');
  });

  it('says a source is ungraded rather than inventing a grade', () => {
    render(<EvidenceChain relationship={base} />);
    expect(screen.getByText('Ungraded')).toBeInTheDocument();
  });

  it('uses the document reliability as the grade when one exists', () => {
    render(
      <EvidenceChain
        relationship={base}
        document={{ id: 'd1', name: 'Threat report', reliability: 'B2' }}
      />,
    );
    expect(screen.queryByText('Ungraded')).not.toBeInTheDocument();
    expect(screen.getAllByText('B2').length).toBeGreaterThan(0);
  });

  it('does not dress a single source up as corroborated', () => {
    render(<EvidenceChain relationship={base} />);
    expect(screen.getByText('Single source')).toBeInTheDocument();
    expect(screen.queryByText('Sources agree')).not.toBeInTheDocument();
  });

  it('surfaces a conflict between multiple sources', () => {
    render(
      <EvidenceChain
        relationship={{ ...base, corroboration_count: 3, corroboration_agreement: 'CONFLICT' }}
      />,
    );
    expect(screen.getByText('3 sources')).toBeInTheDocument();
    expect(screen.getByText('Sources conflict')).toBeInTheDocument();
  });

  it('is explicit when no source sentence was captured', () => {
    render(<EvidenceChain relationship={{ ...base, evidence: '' }} />);
    expect(screen.getByText(/No source sentence was captured/)).toBeInTheDocument();
  });

  it('opens the source document when asked', async () => {
    const onOpen = vi.fn();
    render(
      <EvidenceChain
        relationship={base}
        document={{ id: 'doc-9', name: 'Rotterdam report' }}
        onOpenDocument={onOpen}
      />,
    );
    await userEvent.click(screen.getByText('Rotterdam report'));
    expect(onOpen).toHaveBeenCalledWith('doc-9');
  });
});
