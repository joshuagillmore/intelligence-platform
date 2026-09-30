'use client';
import { useEffect, useState } from 'react';
import { useProject } from '@/lib/ProjectContext';
import { healthApi } from '@/lib/api';
import { readHealth, type HealthLevel } from '@/lib/health';

const LABEL: Record<HealthLevel, string> = {
  checking: 'Checking',
  ok: 'Systems Nominal',
  degraded: 'Degraded',
  down: 'Disconnected',
};

const DOT: Record<HealthLevel, string> = {
  checking: 'bg-gray-500',
  ok: 'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.4)]',
  degraded: 'bg-yellow-500',
  down: 'bg-red-500',
};

export default function StatusBar() {
  const { activeProject } = useProject();
  const [level, setLevel] = useState<HealthLevel>('checking');
  const [detail, setDetail] = useState('');
  const [lastAction, setLastAction] = useState('Ready');

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        const res = await healthApi.check();
        if (cancelled) return;
        const reading = readHealth(res?.data);
        setLevel(reading.level);
        setDetail(reading.detail);
        setLastAction(`Last check: ${new Date().toLocaleTimeString()}`);
      } catch {
        if (cancelled) return;
        setLevel('down');
        setDetail('');
      }
    };
    check();
    const interval = setInterval(check, 30000);
    return () => { cancelled = true; clearInterval(interval); };
  }, []);

  return (
    <div className="fixed bottom-0 left-56 right-0 h-7 bg-[#090e1c] border-t border-navy-800 hidden md:flex items-center px-4 text-[9px] tracking-widest uppercase gap-6 z-50">
      <div className="flex items-center gap-1.5">
        <div className={`w-1.5 h-1.5 rounded-full ${DOT[level]}`} />
        <span className="text-gray-500 font-bold">
          {LABEL[level]}
          {detail && <span className="text-yellow-500/80 font-normal"> · {detail}</span>}
        </span>
      </div>
      {activeProject && (
        <span className="text-gray-500">
          Project: <span className="text-gray-400 font-bold">{activeProject.name}</span>
        </span>
      )}
      <span className="ml-auto text-gray-600">{lastAction}</span>
    </div>
  );
}
