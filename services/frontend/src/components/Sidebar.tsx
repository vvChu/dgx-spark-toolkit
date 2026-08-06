import { Layout, MessageSquare, Share2, Activity, FileCheck, LucideIcon } from 'lucide-react';

interface Tab {
  id: string;
  icon: LucideIcon;
}

const tabs: Tab[] = [
  { id: 'chat', icon: MessageSquare },
  { id: 'graph', icon: Share2 },
  { id: 'benchmarking', icon: Activity },
  { id: 'compliance', icon: FileCheck },
];

interface SidebarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
}

export default function Sidebar({ activeTab, setActiveTab }: SidebarProps) {
  return (
    <nav role="navigation" aria-label="Main navigation" className="w-20 glass flex flex-col items-center py-8 space-y-8 border-r border-[#313244] z-50">
      <div className="p-3 bg-blue-500/20 rounded-xl text-blue-500 mb-4 shadow-lg shadow-blue-500/10" aria-hidden="true">
        <Layout size={28} />
      </div>
      {tabs.map(({ id, icon: Icon }) => (
        <button
          key={id}
          onClick={() => setActiveTab(id)}
          aria-label={`Switch to ${id} tab`}
          aria-current={activeTab === id ? 'page' : undefined}
          className={`p-3 rounded-xl transition-all duration-300 ${
            activeTab === id
              ? 'bg-blue-500 text-white shadow-xl shadow-blue-500/40 scale-110'
              : 'text-gray-500 hover:text-gray-200 hover:bg-white/5'
          }`}
        >
          <Icon size={24} />
        </button>
      ))}
    </nav>
  );
}
