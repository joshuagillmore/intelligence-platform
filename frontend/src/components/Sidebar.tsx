'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

const navItems = [
  { name: 'Projects', href: '/', icon: '📁' },
  { name: 'Collections', href: '/collections', icon: '📡' },
  { name: 'Data Sources', href: '/data-sources', icon: '🌳' },
  { name: 'Network Analysis', href: '/network', icon: '🔗' },
  { name: 'Geo-Intelligence', href: '/geo', icon: '🌍' },
  { name: 'Cyber', href: '/cyber', icon: '🛡️' },
  { name: 'Products', href: '/products', icon: '📄' },
  { name: 'LLM Hub', href: '/llm-hub', icon: '🤖' },
  { name: 'Admin', href: '/admin', icon: '⚙️' },
];

export default function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="w-56 bg-navy-800 border-r border-navy-600 flex flex-col h-screen fixed left-0 top-0">
      <div className="p-4 border-b border-navy-600">
        <h1 className="text-lg font-bold text-accent-blue">Intel Platform</h1>
        <p className="text-xs text-gray-500 mt-1">Analyst Workbench</p>
      </div>
      <nav className="flex-1 py-2">
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
            <span>{item.icon}</span>
            <span>{item.name}</span>
          </Link>
        ))}
      </nav>
    </aside>
  );
}
