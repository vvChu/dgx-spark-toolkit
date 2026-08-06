import { RefObject } from 'react';
import { Search, FileText, Activity, ThumbsUp, ThumbsDown, CheckCircle2, Loader2 } from 'lucide-react';
import { motion } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import EvalBadge from './EvalBadge';
import type { Message } from '../hooks/useChat';
import type { Evaluation } from '../hooks/useEvaluation';
import type { GraphNode } from '../lib/api';

interface ChatPanelProps {
  messages: Message[];
  input: string;
  setInput: (value: string) => void;
  isLoading: boolean;
  evaluation: Evaluation | null;
  handleSendMessage: () => void;
  handleFeedback: (msgIndex: number, isPositive: boolean) => void;
  handleNodeClick: (node: GraphNode, bbox?: number[] | null) => void;
  chatEndRef: RefObject<HTMLDivElement | null>;
}

export default function ChatPanel({
  messages, input, setInput, isLoading, evaluation,
  handleSendMessage, handleFeedback, handleNodeClick, chatEndRef,
}: ChatPanelProps) {
  return (
    <motion.div
      key="chat"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      className="h-full flex flex-col max-w-5xl mx-auto p-8"
    >
      {/* Message list */}
      <div className="flex-1 overflow-y-auto space-y-8 pr-4 custom-scrollbar">
        {messages.map((m, i) => (
          <div key={m.id || i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] p-5 rounded-3xl shadow-2xl transition-all ${m.role === 'user' ? 'bg-blue-600 text-white' : 'glass border-blue-500/20'}`}>
              {m.thought && (
                <div className="mb-4 p-3 rounded-xl bg-blue-950/40 border border-blue-500/20 text-xs text-blue-200/80 space-y-1">
                  <div className="flex items-center space-x-2 opacity-80">
                    <Activity size={12} className="text-blue-400 animate-pulse" />
                    <span className="text-[10px] uppercase font-bold tracking-wider">AI Reasoning Path</span>
                  </div>
                  <div className="text-[11px] leading-relaxed font-mono opacity-90 whitespace-pre-wrap max-h-32 overflow-y-auto custom-scrollbar">
                    {m.thought}
                  </div>
                </div>
              )}
              <div className="text-[15px] leading-relaxed prose prose-invert max-w-none prose-table:border-collapse prose-th:border prose-th:border-white/20 prose-th:p-2 prose-td:border prose-td:border-white/20 prose-td:p-2">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
              </div>

              {m.role === 'ai' && m.context && (
                <div className="mt-4 pt-4 border-t border-white/5 flex items-center justify-between">
                  <div className="flex space-x-2">
                    {m.context.slice(0, 3).map((c, idx) => (
                      <button
                        key={idx}
                        onClick={() => handleNodeClick({ id: c.source, page: c.page }, c.bbox)}
                        className="flex items-center space-x-1 px-2 py-1 bg-white/5 hover:bg-white/10 rounded-md text-[10px] text-gray-400 transition-colors border border-white/5 hover:border-blue-500/50"
                      >
                        <FileText size={10} />
                        <span>{c.source.split('_')[1] || c.source} (p.{c.page})</span>
                      </button>
                    ))}
                  </div>
                  <FeedbackButtons msg={m} msgIndex={i} onFeedback={handleFeedback} />
                </div>
              )}
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="flex justify-start">
            <div className="glass p-4 rounded-2xl flex items-center space-x-3">
              <Loader2 className="animate-spin text-blue-500" size={18} />
              <span className="text-xs font-medium text-gray-400">Spark is thinking...</span>
            </div>
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      <EvalBadge evaluation={evaluation} />

      {/* Input bar */}
      <div className="mt-8 relative group">
        <div className="absolute -inset-1 bg-gradient-to-r from-blue-500/50 to-green-500/50 rounded-2xl blur opacity-25 group-hover:opacity-50 transition duration-1000" />
        <div className="relative flex bg-[#1e1e2e] border border-[#313244] rounded-2xl shadow-2xl overflow-hidden">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
            placeholder="Tra c\u1EE9u m\u1ED1i li\u00EAn h\u1EC7 ho\u1EB7c n\u1ED9i dung v\u0103n b\u1EA3n ph\u00E1p lu\u1EADt..."
            aria-label="Search legal documents"
            className="flex-1 bg-transparent px-6 py-4 text-sm focus:outline-none placeholder:text-gray-600"
          />
          <button
            onClick={handleSendMessage}
            aria-label="Send message"
            className="px-6 bg-blue-500 hover:bg-blue-500/80 text-white transition-all flex items-center justify-center"
          >
            <Search size={22} />
          </button>
        </div>
      </div>
    </motion.div>
  );
}

interface FeedbackButtonsProps {
  msg: Message;
  msgIndex: number;
  onFeedback: (msgIndex: number, isPositive: boolean) => void;
}

function FeedbackButtons({ msg, msgIndex, onFeedback }: FeedbackButtonsProps) {
  if (msg.feedback) {
    return (
      <div className="text-[10px] font-bold text-blue-500 animate-pulse flex items-center space-x-1">
        <CheckCircle2 size={12} />
        <span>Thanks!</span>
      </div>
    );
  }
  return (
    <div className="flex items-center space-x-3">
      <button onClick={() => onFeedback(msgIndex, true)} aria-label="Helpful" className="p-1.5 hover:bg-white/10 rounded-lg text-gray-500 hover:text-green-500 transition-colors">
        <ThumbsUp size={14} />
      </button>
      <button onClick={() => onFeedback(msgIndex, false)} aria-label="Not helpful" className="p-1.5 hover:bg-white/10 rounded-lg text-gray-500 hover:text-red-500 transition-colors">
        <ThumbsDown size={14} />
      </button>
    </div>
  );
}
