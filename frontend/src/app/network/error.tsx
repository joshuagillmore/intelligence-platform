'use client';
import { useEffect } from 'react';
import Sidebar from '@/components/Sidebar';

/**
 * Error boundary for the network view. A render-time exception here (the d3
 * canvas included) used to take the route down to Next's bare error page with
 * no way back but a reload; this keeps the shell and offers a retry.
 */
export default function NetworkError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error('Network view failed to render', error);
  }, [error]);

  return (
    <div className="flex">
      <Sidebar />
      <main className="md:ml-56 flex-1 p-8 pt-14 md:pt-8">
        <h2 className="text-2xl font-bold mb-4">Network Analysis</h2>
        <div className="bg-navy-800 border border-navy-600 rounded-lg p-8 text-center">
          <p className="text-lg text-gray-200 mb-2">The network view failed to render.</p>
          <p className="text-sm text-gray-500 mb-4">Nothing in the project was changed. Try again; if it recurs, clear the filters that were active.</p>
          <button
            onClick={reset}
            className="bg-accent-blue hover:bg-blue-600 text-white px-4 py-2 rounded text-sm font-medium transition-colors"
          >
            Try again
          </button>
        </div>
      </main>
    </div>
  );
}
