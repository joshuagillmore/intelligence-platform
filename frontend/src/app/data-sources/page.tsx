'use client';
import Sidebar from '@/components/Sidebar';

export default function DataSourcesPage() {
  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-56 flex-1 p-8">
        <h2 className="text-2xl font-bold mb-4">Data Sources</h2>
        <div className="bg-navy-800 border border-navy-600 rounded-lg p-8 text-center text-gray-500">
          <p className="text-lg mb-2">Document Explorer</p>
          <p className="text-sm">Topic tree and document explorer</p>
        </div>
      </main>
    </div>
  );
}
