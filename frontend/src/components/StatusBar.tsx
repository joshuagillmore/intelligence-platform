'use client';
import { useEffect, useState } from 'react';
import { useProject } from '@/lib/ProjectContext';

export default function StatusBar() {
  const { activeProject } = useProject();
  const [connected, setConnected] = useState(true);
  const [lastAction, setLastAction] = useState('Ready');

  useEffect(() => {
    const check = async () => {
      try {
        const res = await fetch('http://localhost:8000/health');
        setConnected(res.ok);
        if (res.ok) {
          setLastAction(`Last check: ${new Date().toLocaleTimeString()}`);
        }
      } catch {
        setConnected(false);
      }
    };
    check();
    const interval = setInterval(check, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="fixed bottom-0 left-56 right-0 h-7 bg-[#090e1c] border-t border-[#1a1f2e] hidden md:flex items-center px-4 text-[9px] tracking-widest uppercase gap-6 z-50">
      <div className="flex items-center gap-1.5">
        <div className={`w-1.5 h-1.5 rounded-full ${connected ? 'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.4)]' : 'bg-red-500'}`} />
        <span className="text-gray-500 font-bold">{connected ? 'Systems Nominal' : 'Disconnected'}</span>
      </div>
      {activeProject && (
        <span className="text-gray-500">
          Project: <span className="text-gray-400 font-bold">{activeProject.name}</span>
        </span>
      )}
      <div className="flex items-center gap-1.5">
        <span className="material-symbols-outlined text-[10px] text-[#adc6ff]">shield</span>
        <span className="text-gray-500">Encryption: AES-256</span>
      </div>
      <span className="ml-auto text-gray-600">{lastAction}</span>
    </div>
  );
}
