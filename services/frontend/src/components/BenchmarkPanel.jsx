import { Activity, Loader2 } from 'lucide-react';
import { motion } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import { GRAFANA_URL } from '../lib/api';
import { MetricBadge } from './ui/MetricBadge';
import { LoadingButton } from './ui/LoadingButton';

const BENCHMARK_MODELS = ['qwen3.5-35b', 'claude-sonnet-4-6', 'gemini-3.1-pro'];

export default function BenchmarkPanel({
  compareMode, setCompareMode,
  benchmarkInput, setBenchmarkInput,
  isBenchmarking, benchmarkResults,
  evalHistory, handleRunBenchmark,
}) {
  return (
    <motion.div
      key="benchmarking"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="h-full flex flex-col p-8 max-w-6xl mx-auto"
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-2xl font-bold">RAG Evaluation Benchmarking</h2>
          <p className="text-xs text-gray-500 mt-1">Compare model performance on the same query</p>
        </div>
        <div className="flex space-x-4">
          <button
            onClick={() => setCompareMode(!compareMode)}
            className={`px-4 py-2 rounded-lg text-sm font-bold border transition-all ${
              compareMode ? 'bg-blue-600 border-blue-500 text-white' : 'glass border-white/10 text-gray-400'
            }`}
          >
            {compareMode ? 'Exit Comparison' : 'Compare Models'}
          </button>
          <a
            href={`${GRAFANA_URL}/d/rag-dgx/rag-pipeline-dgx-spark-monitoring`}
            target="_blank"
            rel="noreferrer"
            className="px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-sm font-bold flex items-center space-x-2 hover:bg-white/10"
          >
            <span>Grafana</span>
            <Activity size={16} />
          </a>
        </div>
      </div>

      {compareMode ? (
        <CompareView
          benchmarkInput={benchmarkInput}
          setBenchmarkInput={setBenchmarkInput}
          isBenchmarking={isBenchmarking}
          benchmarkResults={benchmarkResults}
          handleRunBenchmark={handleRunBenchmark}
        />
      ) : (
        <HistoryView evalHistory={evalHistory} />
      )}
    </motion.div>
  );
}

function CompareView({ benchmarkInput, setBenchmarkInput, isBenchmarking, benchmarkResults, handleRunBenchmark }) {
  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex space-x-4 mb-6">
        <input
          type="text"
          value={benchmarkInput}
          onChange={(e) => setBenchmarkInput(e.target.value)}
          placeholder="Enter a complex legal query for benchmarking..."
          className="flex-1 glass border-white/10 rounded-xl px-6 py-3 text-sm focus:outline-none"
        />
        <LoadingButton
          onClick={handleRunBenchmark}
          loading={isBenchmarking}
          disabled={!benchmarkInput}
          className="px-8 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-xl font-bold transition-all flex items-center space-x-2"
        >
          <Activity size={18} />
          <span>Run All</span>
        </LoadingButton>
      </div>

      <div className="flex-1 overflow-x-auto overflow-y-hidden pb-4 custom-scrollbar">
        <div className="flex space-x-6 h-full min-w-max">
          {BENCHMARK_MODELS.map((model) => (
            <ModelCard key={model} model={model} result={benchmarkResults[model]} isBenchmarking={isBenchmarking} />
          ))}
        </div>
      </div>
    </div>
  );
}

function ModelCard({ model, result, isBenchmarking }) {
  return (
    <div className="w-[400px] flex flex-col glass border-white/10 rounded-3xl p-6">
      <div className="flex items-center justify-between mb-4 pb-4 border-b border-white/5">
        <h3 className="font-bold text-blue-400">{model}</h3>
        {result && (
          <div className={`text-lg font-black ${result.faithfulness > 0.8 ? 'text-green-500' : 'text-yellow-500'}`}>
            {Math.round(result.faithfulness * 100)}%
          </div>
        )}
      </div>

      {result ? (
        <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar space-y-6">
          <div>
            <div className="text-[10px] font-bold text-gray-500 uppercase mb-2">Generated Answer</div>
            <div className="text-[13px] text-gray-300 leading-relaxed bg-white/5 p-4 rounded-xl border border-white/5">
              <ReactMarkdown>{result.answer}</ReactMarkdown>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="bg-white/5 p-3 rounded-xl">
              <div className="text-[9px] font-bold text-blue-500 mb-1 uppercase">Faithfulness</div>
              <p className="text-[11px] text-gray-400 leading-tight">{result.faithfulness_reason}</p>
            </div>
            <div className="bg-white/5 p-3 rounded-xl">
              <div className="text-[9px] font-bold text-green-500 mb-1 uppercase">Relevancy</div>
              <p className="text-[11px] text-gray-400 leading-tight">{result.relevancy_reason}</p>
            </div>
          </div>
        </div>
      ) : (
        <div className="flex-1 flex flex-col items-center justify-center text-gray-600">
          {isBenchmarking ? <Loader2 className="animate-spin mb-4" size={32} /> : <Activity size={32} className="mb-4 opacity-20" />}
          <p className="text-xs">{isBenchmarking ? 'Processing...' : 'Ready to test'}</p>
        </div>
      )}
    </div>
  );
}

function HistoryView({ evalHistory }) {
  if (evalHistory.length === 0) {
    return (
      <div className="h-64 glass flex flex-col items-center justify-center text-gray-500 rounded-3xl border-dashed border-2 border-white/5">
        <Activity size={48} className="mb-4 opacity-20" />
        <p>No evaluations recorded yet. Start a chat to see metrics.</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-6 overflow-y-auto pr-2 custom-scrollbar">
      {evalHistory.map((ev, idx) => (
        <div key={idx} className="glass p-6 rounded-3xl border border-white/5 hover:border-blue-500/30 transition-all">
          <div className="flex items-center justify-between mb-4">
            <div className="text-xs font-bold text-gray-500 uppercase tracking-widest">{ev.timestamp}</div>
            <div className="flex space-x-4">
              <ScoreBadge label="Faithfulness" value={ev.faithfulness} />
              <ScoreBadge label="Relevancy" value={ev.relevancy} />
            </div>
          </div>
          <h3 className="text-sm font-bold text-blue-400 mb-2">Q: {ev.query}</h3>
          <div className="grid grid-cols-2 gap-6 mt-4">
            <div className="bg-white/5 p-4 rounded-xl">
              <div className="text-[10px] font-bold text-blue-500 mb-1 uppercase">Reasoning (Faithfulness)</div>
              <p className="text-[12px] text-gray-400 italic">{ev.faithfulness_reason}</p>
            </div>
            <div className="bg-white/5 p-4 rounded-xl">
              <div className="text-[10px] font-bold text-green-500 mb-1 uppercase">Reasoning (Relevancy)</div>
              <p className="text-[12px] text-gray-400 italic">{ev.relevancy_reason}</p>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function ScoreBadge({ label, value }) {
  return <MetricBadge label={label} value={value} />;
}
