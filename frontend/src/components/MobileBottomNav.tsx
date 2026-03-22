'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

const tabs = [
  { name: 'Projects', href: '/', icon: 'folder', iconFilled: 'folder' },
  { name: 'Maps', href: '/geo', icon: 'map', iconFilled: 'map' },
  { name: 'Cyber', href: '/cyber', icon: 'terminal', iconFilled: 'terminal' },
  { name: 'Alerts', href: '/collections', icon: 'notifications', iconFilled: 'notifications' },
  { name: 'Profile', href: '/admin', icon: 'person', iconFilled: 'person' },
];

export default function MobileBottomNav() {
  const pathname = usePathname();

  function isActive(href: string) {
    if (href === '/') return pathname === '/' || pathname.startsWith('/project/');
    return pathname === href || pathname.startsWith(href + '/');
  }

  // Determine which tabs to show based on current page context
  // Some pages use a 4-tab variant (Collections, Sources, Network, Products)
  const useAltNav = ['/collections', '/data-sources', '/network', '/products'].some(
    p => pathname === p || pathname.startsWith(p + '/')
  );

  const altTabs = [
    { name: 'Collections', href: '/collections', icon: 'folder_open', iconFilled: 'folder_open' },
    { name: 'Sources', href: '/data-sources', icon: 'database', iconFilled: 'database' },
    { name: 'Network', href: '/network', icon: 'hub', iconFilled: 'hub' },
    { name: 'Products', href: '/products', icon: 'description', iconFilled: 'description' },
  ];

  const activeTabs = useAltNav ? altTabs : tabs;

  return (
    <nav className="fixed bottom-0 left-0 w-full z-50 bg-[#0e1321]/95 backdrop-blur-xl border-t border-white/5 shadow-[0_-4px_24px_rgba(0,0,0,0.5)] md:hidden">
      <div className="flex justify-around items-center px-2 pb-[env(safe-area-inset-bottom,8px)] pt-2">
        {activeTabs.map(tab => {
          const active = isActive(tab.href);
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={`flex flex-col items-center justify-center px-3 py-1.5 rounded-xl transition-all active:scale-95 duration-150 ${
                active
                  ? 'text-[#3b82f6] bg-[#3b82f6]/10'
                  : 'text-gray-500 opacity-60 hover:text-blue-300'
              }`}
            >
              <span
                className="material-symbols-outlined text-[22px]"
                style={active ? { fontVariationSettings: "'FILL' 1" } : undefined}
              >
                {active ? tab.iconFilled : tab.icon}
              </span>
              <span className="text-[10px] font-medium tracking-wide mt-0.5">{tab.name}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
