export default function Header({ stats, language, setLanguage }) {
  return (
    <header className="h-16 glass flex items-center justify-between px-8 border-b border-[#313244] shadow-md">
      <div className="flex items-center space-x-4">
        <h1 className="text-xl font-black tracking-tight bg-gradient-to-r from-white via-gray-300 to-gray-500 bg-clip-text text-transparent">
          SPARK BIM GRAPH-RAG
        </h1>
        <div className="h-4 w-[1px] bg-[#313244] mx-2" />
        <div className="flex items-center space-x-2">
          <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
          <span className="text-[11px] font-bold text-green-500 uppercase tracking-widest">
            System Active: {stats.docs} / {stats.total} Docs
          </span>
        </div>
      </div>

      <div className="flex items-center space-x-6">
        <div className="flex bg-white/5 p-1 rounded-lg border border-white/10">
          {['vi', 'en'].map((lang) => (
            <button
              key={lang}
              onClick={() => setLanguage(lang)}
              aria-label={lang === 'vi' ? 'Switch to Vietnamese' : 'Switch to English'}
              aria-pressed={language === lang}
              className={`px-3 py-1 rounded-md text-[10px] font-bold transition-all ${
                language === lang ? 'bg-blue-600 text-white shadow-lg' : 'text-gray-500 hover:text-gray-300'
              }`}
            >
              {lang === 'vi' ? 'Tiếng Việt' : 'English'}
            </button>
          ))}
        </div>
        <div className="flex items-center space-x-8 text-xs font-semibold tracking-wide uppercase text-gray-500">
          <div>Vector Entities: <span className="text-white ml-1">{stats.milvus.toLocaleString()}</span></div>
          <div>Knowledge Edges: <span className="text-white ml-1">{stats.rels}</span></div>
        </div>
      </div>
    </header>
  );
}
