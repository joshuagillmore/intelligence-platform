import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import LoadingSpinner from '@/components/LoadingSpinner';

/**
 * LoadingSpinner is purely presentational — it renders a spinning div whose
 * dimensions vary by the `size` prop. No hooks, network, or context.
 */
describe('LoadingSpinner', () => {
  const spinnerOf = (container: HTMLElement) =>
    container.querySelector('.animate-spin');

  it('renders a spinning element', () => {
    const { container } = render(<LoadingSpinner />);
    expect(spinnerOf(container)).toBeInTheDocument();
  });

  it('defaults to the medium size classes', () => {
    const { container } = render(<LoadingSpinner />);
    const spinner = spinnerOf(container);
    expect(spinner).toHaveClass('w-8', 'h-8');
  });

  it('applies the small size classes when size="sm"', () => {
    const { container } = render(<LoadingSpinner size="sm" />);
    const spinner = spinnerOf(container);
    expect(spinner).toHaveClass('w-4', 'h-4');
    expect(spinner).not.toHaveClass('w-8');
  });

  it('applies the large size classes when size="lg"', () => {
    const { container } = render(<LoadingSpinner size="lg" />);
    expect(spinnerOf(container)).toHaveClass('w-12', 'h-12');
  });
});
