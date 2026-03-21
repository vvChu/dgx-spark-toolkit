import { Layout, MessageSquare, Share2, Activity, FileCheck } from 'lucide-react';

const tabs = [
  { id: 'chat', icon: MessageSquare },
  { id: 'graph', icon: Share2 },
  { id: 'benchmarking', icon: Activity },
  { id: 'compliance', icon: FileCheck },
];

export default function Sidebar({ activeTab, setActiveTab }) {
  return (
    <div className="w-20 glass flex flex-col items-center py-8 space-y-8 border-r border-[#313244] z-50">
      <div className="p-3 bg-blue-500/20 rounded-xl text-blue-500 mb-4 shadow-lg shadow-blue-500/10">
        <Layout size={28} />
      </div>
      {tabs.map(({ id, icon: Icon }) => (
        <button
          key={id}
          onClick={() => setActiveTab(id)}
          className={`p-3 rounded-xl transition-all duration-300 ${
            activeTab === id
              ? 'bg-blue-500 text-white shadow-xl shadow-blue-500/40 scale-110'
              : 'text-gray-500 hover:text-gray-200 hover:bg-white/5'
          }`}
        >
          <Icon size={24} />
        </button>
      ))}
    </div>
  );
}
