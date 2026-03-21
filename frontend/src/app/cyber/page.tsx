'use client';
import Sidebar from '@/components/Sidebar';

export default function CyberPage() {
  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-56 flex-1 p-8">
        <h2 className="text-2xl font-bold mb-4">Cyber Intelligence</h2>
        <div className="bg-navy-800 border border-navy-600 rounded-lg p-8 text-center text-gray-500">
          <p className="text-lg mb-2">Cyber Threat Dashboard</p>
          <p className="text-sm">IOC dashboard, ATT&CK mapping, threat profiles</p>
        </div>
      </main>
    </div>
  );
}
