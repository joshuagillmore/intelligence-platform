import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import Markdown from '@/components/Markdown';

/**
 * Markdown renders untrusted text: scraped documents carry image markdown, and
 * `/query` can return raw retrieved context. An <img> fetches its src the
 * moment it mounts, which would send the analyst's IP and origin to whoever
 * wrote the document, outside the collection proxy. Images must therefore
 * render as their alt text plus an ordinary link the analyst can choose to
 * follow, never as an element that makes a request.
 */
describe('Markdown images', () => {
  it('renders no <img> element for image markdown', () => {
    const { container } = render(
      <Markdown content="Before ![tracking pixel](https://adversary.example/p.png) after" />,
    );
    expect(container.querySelector('img')).toBeNull();
  });

  it('shows the alt text and a plain link to the image source', () => {
    render(<Markdown content="![C2 panel screenshot](https://adversary.example/panel.png)" />);
    expect(screen.getByText(/C2 panel screenshot/)).toBeInTheDocument();
    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', 'https://adversary.example/panel.png');
    expect(link).toHaveAttribute('rel', expect.stringContaining('noreferrer'));
  });

  it('still says there was an image when the alt text is empty', () => {
    const { container } = render(<Markdown content="![](https://adversary.example/x.gif)" />);
    expect(container.querySelector('img')).toBeNull();
    expect(container.textContent).toMatch(/image/i);
  });

  it('renders no <img> for reference-style images either', () => {
    const { container } = render(
      <Markdown content={'![logo][ref]\n\n[ref]: https://adversary.example/logo.png'} />,
    );
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByText(/logo/)).toBeInTheDocument();
  });
});
