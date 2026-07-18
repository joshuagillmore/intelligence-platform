'use client';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function KeyboardShortcuts() {
  const router = useRouter();

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      // Only trigger with Ctrl/Cmd
      if (!e.ctrlKey && !e.metaKey) return;

      switch (e.key) {
        case 'k': // Search
          e.preventDefault();
          const searchInput = document.querySelector('[data-search-input]') as HTMLInputElement;
          if (searchInput) searchInput.focus();
          else router.push('/search'); // mobile: sidebar search is hidden
          break;
        case '1': e.preventDefault(); router.push('/'); break;
        case '2': e.preventDefault(); router.push('/collections'); break;
        case '3': e.preventDefault(); router.push('/network'); break;
        case '4': e.preventDefault(); router.push('/data-sources'); break;
        case '5': e.preventDefault(); router.push('/geo'); break;
        case '6': e.preventDefault(); router.push('/cyber'); break;
      }
    }

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [router]);

  return null;
}
