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
    <div className="fixed bottom-0 left-56 right-0 h-7 bg-navy-800 border-t border-navy-600 flex items-center px-4 text-xs text-gray-500 gap-4 z-50">
      <div className="flex items-center gap-1.5">
        <div className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500' : 'bg-red-500'}`} />
        <span>{connected ? 'Connected' : 'Disconnected'}</span>
      </div>
      {activeProject && (
        <span className="text-gray-400">
          Project: <span className="text-gray-300">{activeProject.name}</span>
        </span>
      )}
      <span className="ml-auto">{lastAction}</span>
    </div>
  );
}
