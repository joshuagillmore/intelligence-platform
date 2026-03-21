'use client';
import { useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useProject } from '@/lib/ProjectContext';

const navItems = [
  { name: 'Projects', href: '/', icon: 'P' },
  { name: 'Collections', href: '/collections', icon: 'C' },
  { name: 'Data Sources', href: '/data-sources', icon: 'D' },
  { name: 'Network Analysis', href: '/network', icon: 'N' },
  { name: 'Timeline', href: '/timeline', icon: 'T' },
  { name: 'Geo-Intelligence', href: '/geo', icon: 'G' },
  { name: 'Cyber', href: '/cyber', icon: 'S' },
  { name: 'Products', href: '/products', icon: 'R' },
  { name: 'LLM Hub', href: '/llm-hub', icon: 'L' },
  { name: 'Admin', href: '/admin', icon: 'A' },
];

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { activeProject } = useProject();
  const [searchQuery, setSearchQuery] = useState('');

  function handleSearchKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' && searchQuery.trim()) {
      router.push(`/search?q=${encodeURIComponent(searchQuery.trim())}`);
      setSearchQuery('');
    }
  }

  return (
    <aside className="w-56 bg-navy-800 border-r border-navy-600 flex flex-col h-screen fixed left-0 top-0">
      <div className="p-4 border-b border-navy-600">
        <h1 className="text-lg font-bold text-accent-blue">Intel Platform</h1>
        <p className="text-xs text-gray-500 mt-1">Analyst Workbench</p>
      </div>
      <div className="px-4 py-2 border-b border-navy-600">
        <p className="text-xs text-gray-500">Active Project</p>
        <p className="text-sm font-medium text-gray-200 truncate">
          {activeProject ? activeProject.name : 'No project selected'}
        </p>
      </div>
      <div className="px-4 py-2 border-b border-navy-600">
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          onKeyDown={handleSearchKeyDown}
          placeholder="Search... (Enter)"
          className="w-full bg-navy-700 border border-navy-600 rounded px-3 py-1.5 text-xs text-gray-200 placeholder-gray-500 focus:outline-none focus:border-accent-blue"
        />
      </div>
      <nav className="flex-1 py-2 overflow-y-auto">
        {navItems.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
              pathname === item.href
                ? 'bg-navy-700 text-accent-blue border-r-2 border-accent-blue'
                : 'text-gray-400 hover:text-gray-200 hover:bg-navy-700'
            }`}
          >
            <span className="w-5 h-5 bg-navy-600 rounded text-xs flex items-center justify-center font-mono">{item.icon}</span>
            <span>{item.name}</span>
          </Link>
        ))}
      </nav>
    </aside>
  );
}
