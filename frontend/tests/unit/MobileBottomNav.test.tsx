import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { ReactNode } from 'react';
import MobileBottomNav from '@/components/MobileBottomNav';

vi.mock('next/navigation', () => ({ usePathname: () => '/' }));
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: ReactNode }) => (
    <a href={href} {...rest}>{children}</a>
  ),
}));

// Node's own global localStorage is undefined unless started with a storage
// file, and it shadows jsdom's; the component reads the role from it on mount.
beforeEach(() => {
  const data = new Map<string, string>();
  Object.defineProperty(window, 'localStorage', {
    configurable: true,
    value: {
      getItem: (k: string) => (data.has(k) ? data.get(k)! : null),
      setItem: (k: string, v: string) => { data.set(k, String(v)); },
      removeItem: (k: string) => { data.delete(k); },
      clear: () => data.clear(),
      key: (i: number) => [...data.keys()][i] ?? null,
      get length() { return data.size; },
    },
  });
});

/** A real tap: mousedown, then click, on the same button. */
function tap(el: HTMLElement) {
  fireEvent.mouseDown(el);
  fireEvent.mouseUp(el);
  fireEvent.click(el);
}

describe('MobileBottomNav menu', () => {
  it('opens on tap', () => {
    render(<MobileBottomNav />);
    tap(screen.getByRole('button', { name: /open navigation menu/i }));
    expect(screen.getByText('All Pages')).toBeInTheDocument();
  });

  it('closes when the Close button is tapped (it used to re-open)', () => {
    render(<MobileBottomNav />);
    tap(screen.getByRole('button', { name: /open navigation menu/i }));
    tap(screen.getByRole('button', { name: /close navigation menu/i }));
    expect(screen.queryByText('All Pages')).toBeNull();
  });

  it('closes on a tap outside the menu', () => {
    render(<MobileBottomNav />);
    tap(screen.getByRole('button', { name: /open navigation menu/i }));
    fireEvent.mouseDown(document.body);
    expect(screen.queryByText('All Pages')).toBeNull();
  });
});
