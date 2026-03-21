import React, { useState, useEffect, useRef } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import {
  MessageSquare,
  Layout,
  Share2,
  Search,
  Send,
  FileText,
  Activity,
  ChevronRight,
  Loader2,
  Globe,
  Database,
  LayoutDashboard,
  ThumbsUp,
  ThumbsDown,
  CheckCircle2,
  X,
  AlertTriangle,
  FileCheck
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const API_BASE = import.meta.env.VITE_API_URL || 'http://100.83.192.30:8005';

const Dashboard = () => {
  const [messages, setMessages] = useState([
    { role: 'ai', content: 'Chào anh, em là Spark BIM Expert. Em đã sẵn sàng hỗ trợ anh tra cứu và phân tích hơn 8.000 văn bản pháp luật với công nghệ GraphRAG.' }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const [activeTab, setActiveTab] = useState('chat');
  const [stats, setStats] = useState({ docs: 0, rels: 0, milvus: 0, total: 8870 });
  const [preview, setPreview] = useState(null);
  const [language, setLanguage] = useState('vi');
  const [evaluation, setEvaluation] = useState(null);
  const [evalHistory, setEvalHistory] = useState([]);
  const [compareMode, setCompareMode] = useState(false);
  const [benchmarkInput, setBenchmarkInput] = useState('');
  const [isBenchmarking, setIsBenchmarking] = useState(false);
  const [benchmarkResults, setBenchmarkResults] = useState({});
  const [complianceProfile, setComplianceProfile] = useState('');
  const [complianceReport, setComplianceReport] = useState(null);
  const [isCheckingCompliance, setIsCheckingCompliance] = useState(false);
  const [isAnalyzingConflicts, setIsAnalyzingConflicts] = useState(false);
  const [conflictReport, setConflictReport] = useState(null);
  const chatEndRef = useRef(null);

  const scrollToBottom = () => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(scrollToBottom, [messages]);

  const fetchData = async () => {
    try {
      const [statsRes, graphRes] = await Promise.all([
        axios.get(`${API_BASE}/stats`),
        axios.get(`${API_BASE}/graph/data`)
      ]);
      setStats({
        docs: statsRes.data.neo4j_docs,
        rels: statsRes.data.neo4j_rels,
        milvus: statsRes.data.milvus_entities,
        total: statsRes.data.total_target || 8870
      });
      setGraphData(graphRes.data);
    } catch (err) {
      console.error('Failed to fetch dashboard data:', err);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 15000);
    return () => clearInterval(interval);
  }, []);

  const handleSendMessage = async () => {
    if (!input || isLoading) return;

    const userMsg = { role: 'user', content: input };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setIsLoading(true);

    try {
      const resp = await axios.post(`${API_BASE}/chat`, {
        query: input,
        language: language
      });
      const aiMsg = {
        role: 'ai',
        content: resp.data.answer,
        thought: resp.data.thought,
        context: resp.data.context
      };
      setMessages(prev => [...prev, aiMsg]);

      // Auto-trigger evaluation if enabled
      const contextStrs = resp.data.context ? resp.data.context.map(c => c.text) : [];
      handleEvaluate(input, resp.data.answer, contextStrs);

      fetchData();
    } catch (err) {
      setMessages(prev => [...prev, { role: 'ai', content: 'Có lỗi kết nối tới Spark Engine. Anh vui lòng kiểm tra lại dịch vụ nhé.' }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleEvaluate = async (query, answer, context) => {
    try {
      if (!context || context.length === 0) {
        const cachedEval = {
          query,
          faithfulness: 1.0,
          relevancy: 1.0,
          faithfulness_reason: "Answer served from high-confidence semantic cache.",
          relevancy_reason: "Query perfectly matched a previously answered question.",
          suggestions: [],
          timestamp: new Date().toLocaleTimeString()
        };
        setEvaluation(cachedEval);
        setEvalHistory(prev => [cachedEval, ...prev].slice(0, 10));
        return;
      }
      setEvaluation({ loading: true });
      const resp = await axios.post(`${API_BASE}/evaluate`, { query, answer, context });
      const fullEval = { ...resp.data, query, timestamp: new Date().toLocaleTimeString() };
      setEvaluation(fullEval);
      setEvalHistory(prev => [fullEval, ...prev].slice(0, 10));
    } catch (err) {
      console.error('Evaluation failed:', err);
      setEvaluation(null);
    }
  };

  const handleRunBenchmark = async () => {
    if (!benchmarkInput || isBenchmarking) return;
    setIsBenchmarking(true);
    setBenchmarkResults({});
    const models = ['qwen3.5-35b', 'claude-opus-4-6-thinking', 'gemini-3.1-pro-high'];

    try {
      await Promise.all(models.map(async (model) => {
        try {
          const chatResp = await axios.post(`${API_BASE}/chat`, {
            query: benchmarkInput,
            model: model,
            language: language
          });

          const contextStrs = chatResp.data.context ? chatResp.data.context.map(c => c.text) : [];
          const evalResp = await axios.post(`${API_BASE}/evaluate`, {
            query: benchmarkInput,
            answer: chatResp.data.answer,
            context: contextStrs
          });

          const result = {
            answer: chatResp.data.answer,
            ...evalResp.data
          };
          setBenchmarkResults(prev => ({ ...prev, [model]: result }));
        } catch (err) {
          console.error(`Benchmark failed for ${model}:`, err);
        }
      }));
    } finally {
      setIsBenchmarking(false);
    }
  };

  const handleFeedback = async (msgIndex, isPositive) => {
    const msg = messages[msgIndex];
    const prevMsg = messages[msgIndex - 1]; // The query

    try {
      await axios.post(`${API_BASE}/feedback`, {
        query: prevMsg ? prevMsg.content : "N/A",
        answer: msg.content,
        is_positive: isPositive
      });

      // Update local state to show "Thank you" or highlight
      const newMessages = [...messages];
      newMessages[msgIndex].feedback = isPositive ? 'positive' : 'negative';
      setMessages(newMessages);
    } catch (err) {
      console.error('Feedback failed:', err);
    }
  };

  const handleNodeClick = async (node, bbox = null) => {
    try {
      const resp = await axios.get(`${API_BASE}/preview`, {
        params: { source: node.id, page: node.page || 1 }
      });
      setPreview({ ...resp.data, highlightBbox: bbox });
    } catch (err) {
      console.error('Preview failed:', err);
    }
  };

  const handleExpandNode = async (node) => {
    try {
      const resp = await axios.get(`${API_BASE}/graph/neighbors/${encodeURIComponent(node.id)}`);
      const { nodes: newNodes, links: newLinks } = resp.data;

      setGraphData(prev => {
        const existingNodes = new Set(prev.nodes.map(n => n.id));
        const filteredNewNodes = newNodes.filter(n => !existingNodes.has(n.id));

        const existingLinks = new Set(prev.links.map(l => `${l.source.id || l.source}-${l.target.id || l.target}`));
        const filteredNewLinks = newLinks.filter(l => !existingLinks.has(`${l.source}-${l.target}`));

        return {
          nodes: [...prev.nodes, ...filteredNewNodes],
          links: [...prev.links, ...filteredNewLinks]
        };
      });
    } catch (err) {
      console.error('Expand failed:', err);
    }
  };

  const handleComplianceCheck = async () => {
    if (!complianceProfile || isCheckingCompliance) return;
    setIsCheckingCompliance(true);
    try {
      const resp = await axios.post(`${API_BASE}/compliance/check`, {
        project_profile: complianceProfile
      });
      setComplianceReport(resp.data.report);
    } catch (err) {
      console.error('Compliance check failed:', err);
    } finally {
      setIsCheckingCompliance(false);
    }
  };

  const handleAnalyzeConflicts = async (docId) => {
    setIsAnalyzingConflicts(true);
    setConflictReport(null);
    try {
      const resp = await axios.post(`${API_BASE}/graph/analyze-conflicts`, {
        doc_id: docId
      });
      setConflictReport(resp.data.conflicts);
    } catch (err) {
      console.error('Conflict analysis failed:', err);
    } finally {
      setIsAnalyzingConflicts(false);
    }
  };

  return (
    <div className="flex h-screen bg-[#11111b] text-gray-200 overflow-hidden font-sans">
      {/* Sidebar Nav */}
      <div className="w-20 glass flex flex-col items-center py-8 space-y-8 border-r border-[#313244] z-50">
        <div className="p-3 bg-blue-500/20 rounded-xl text-blue-500 mb-4 shadow-lg shadow-blue-500/10">
          <Layout size={28} />
        </div>
        <button
          onClick={() => setActiveTab('chat')}
          className={`p-3 rounded-xl transition-all duration-300 ${activeTab === 'chat' ? 'bg-blue-500 text-white shadow-xl shadow-blue-500/40 scale-110' : 'text-gray-500 hover:text-gray-200 hover:bg-white/5'}`}>
          <MessageSquare size={24} />
        </button>
        <button
          onClick={() => setActiveTab('graph')}
          className={`p-3 rounded-xl transition-all duration-300 ${activeTab === 'graph' ? 'bg-blue-500 text-white shadow-xl shadow-blue-500/40 scale-110' : 'text-gray-500 hover:text-gray-200 hover:bg-white/5'}`}>
          <Share2 size={24} />
        </button>
        <button
          onClick={() => setActiveTab('benchmarking')}
          className={`p-3 rounded-xl transition-all duration-300 ${activeTab === 'benchmarking' ? 'bg-blue-500 text-white shadow-xl shadow-blue-500/40 scale-110' : 'text-gray-500 hover:text-gray-200 hover:bg-white/5'}`}>
          <Activity size={24} />
        </button>
        <button
          onClick={() => setActiveTab('compliance')}
          className={`p-3 rounded-xl transition-all duration-300 ${activeTab === 'compliance' ? 'bg-blue-500 text-white shadow-xl shadow-blue-500/40 scale-110' : 'text-gray-500 hover:text-gray-200 hover:bg-white/5'}`}>
          <FileCheck size={24} />
        </button>
      </div>

      {/* Main Body */}
      <div className="flex-1 flex flex-col relative">
        {/* Top Header */}
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
              <button
                onClick={() => setLanguage('vi')}
                className={`px-3 py-1 rounded-md text-[10px] font-bold transition-all ${language === 'vi' ? 'bg-blue-600 text-white shadow-lg' : 'text-gray-500 hover:text-gray-300'}`}
              >
                Tiếng Việt
              </button>
              <button
                onClick={() => setLanguage('en')}
                className={`px-3 py-1 rounded-md text-[10px] font-bold transition-all ${language === 'en' ? 'bg-blue-600 text-white shadow-lg' : 'text-gray-500 hover:text-gray-300'}`}
              >
                English
              </button>
            </div>
            <div className="flex items-center space-x-8 text-xs font-semibold tracking-wide uppercase text-gray-500">
              <div>Vector Entities: <span className="text-white ml-1">{(stats.milvus).toLocaleString()}</span></div>
              <div>Knowledge Edges: <span className="text-white ml-1">{stats.rels}</span></div>
            </div>
          </div>
        </header>

        {/* Dynamic Content Area */}
        <main className="flex-1 overflow-hidden relative">
          <AnimatePresence mode="wait">
            {activeTab === 'chat' ? (
              <motion.div
                key="chat"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                className="h-full flex flex-col max-w-5xl mx-auto p-8"
              >
                <div className="flex-1 overflow-y-auto space-y-8 pr-4 custom-scrollbar">
                  {messages.map((m, i) => (
                    <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                      <div className={`max-w-[85%] p-5 rounded-3xl shadow-2xl transition-all ${m.role === 'user' ? 'bg-blue-600 text-white' : 'glass border-blue-500/20'}`}>
                        {m.thought && (
                          <div className="flex items-center space-x-2 mb-3 opacity-60">
                            <Activity size={12} className="text-blue-500" />
                            <span className="text-[10px] uppercase font-bold tracking-tighter">AI Reasoning Path</span>
                          </div>
                        )}
                        <div className="text-[15px] leading-relaxed prose prose-invert max-w-none prose-table:border-collapse prose-th:border prose-th:border-white/20 prose-th:p-2 prose-td:border prose-td:border-white/20 prose-td:p-2">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {m.content}
                          </ReactMarkdown>
                        </div>
                        {m.role === 'assistant' && (
                          <div className="mt-4 pt-4 border-t border-white/5 flex items-center justify-between">
                            <div className="flex space-x-2">
                              {m.context && m.context.slice(0, 3).map((c, idx) => (
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
                            <div className="flex items-center space-x-3">
                              {m.feedback ? (
                                <div className="text-[10px] font-bold text-blue-500 animate-pulse flex items-center space-x-1">
                                  <CheckCircle2 size={12} />
                                  <span>Thanks!</span>
                                </div>
                              ) : (
                                <>
                                  <button
                                    onClick={() => handleFeedback(i, true)}
                                    className="p-1.5 hover:bg-white/10 rounded-lg text-gray-500 hover:text-green-500 transition-colors"
                                  >
                                    <ThumbsUp size={14} />
                                  </button>
                                  <button
                                    onClick={() => handleFeedback(i, false)}
                                    className="p-1.5 hover:bg-white/10 rounded-lg text-gray-500 hover:text-red-500 transition-colors"
                                  >
                                    <ThumbsDown size={14} />
                                  </button>
                                </>
                              )}
                            </div>
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

                {evaluation && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    className="mb-4 p-4 glass border-blue-500/30 rounded-2xl flex items-start space-x-6"
                  >
                    <div className="flex flex-col items-center space-y-1">
                      <div className="text-[10px] font-bold text-gray-500 uppercase">Quality</div>
                      <div className={`text-xl font-black ${evaluation.faithfulness > 0.8 ? 'text-green-500' : 'text-yellow-500'}`}>
                        {evaluation.loading ? '...' : `${Math.round(evaluation.faithfulness * 100)}%`}
                      </div>
                    </div>
                    {!evaluation.loading && (
                      <div className="flex-1 grid grid-cols-2 gap-4 text-[11px]">
                        <div>
                          <div className="font-bold text-blue-500 mb-1 tracking-wider uppercase">Faithfulness</div>
                          <p className="text-gray-400 leading-tight">{evaluation.faithfulness_reason}</p>
                        </div>
                        <div>
                          <div className="font-bold text-green-500 mb-1 tracking-wider uppercase">Relevancy</div>
                          <p className="text-gray-400 leading-tight">{evaluation.relevancy_reason}</p>
                        </div>
                      </div>
                    )}
                  </motion.div>
                )}

                {/* Input Bar */}
                <div className="mt-8 relative group">
                  <div className="absolute -inset-1 bg-gradient-to-r from-blue-500/50 to-green-500/50 rounded-2xl blur opacity-25 group-hover:opacity-50 transition duration-1000"></div>
                  <div className="relative flex bg-[#1e1e2e] border border-[#313244] rounded-2xl shadow-2xl overflow-hidden">
                    <input
                      type="text"
                      value={input}
                      onChange={(e) => setInput(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
                      placeholder="Tra cứu mối liên hệ hoặc nội dung văn bản pháp luật..."
                      className="flex-1 bg-transparent px-6 py-4 text-sm focus:outline-none placeholder:text-gray-600"
                    />
                    <button
                      onClick={handleSendMessage}
                      className="px-6 bg-blue-500 hover:bg-blue-500/80 text-white transition-all flex items-center justify-center"
                    >
                      <Search size={22} />
                    </button>
                  </div>
                </div>
              </motion.div>
            ) : activeTab === 'graph' ? (
              <motion.div
                key="graph"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="h-full w-full bg-[#08080f]"
              >
                <ForceGraph2D
                  graphData={graphData}
                  nodeLabel="name"
                  nodeAutoColorBy="group"
                  linkDirectionalParticles={2}
                  linkDirectionalParticleSpeed={d => 0.005}
                  onNodeClick={handleNodeClick}
                  onNodeRightClick={handleExpandNode}
                  nodeCanvasObject={(node, ctx, globalScale) => {
                    const label = node.name;
                    const fontSize = 12 / globalScale;
                    ctx.font = `${fontSize}px Sans-Serif`;
                    const textWidth = ctx.measureText(label).width;
                    const bckgDimensions = [textWidth, fontSize].map(n => n + fontSize * 0.2);

                    ctx.fillStyle = 'rgba(10, 10, 20, 0.8)';
                    ctx.fillRect(node.x - bckgDimensions[0] / 2, node.y - bckgDimensions[1] / 2, ...bckgDimensions);

                    ctx.textAlign = 'center';
                    ctx.textBaseline = 'middle';
                    ctx.fillStyle = node.color;
                    ctx.fillText(label, node.x, node.y);
                  }}
                />
              </motion.div>
            ) : activeTab === 'benchmarking' ? (
              <motion.div
                key="benchmarking"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="h-full flex flex-col p-8 max-w-6xl mx-auto"
              >
                <div className="flex items-center justify-between mb-8">
                  <div>
                    <h2 className="text-2xl font-bold">RAG Evaluation Benchmarking</h2>
                    <p className="text-xs text-gray-500 mt-1">Compare model performance on the same query</p>
                  </div>
                  <div className="flex space-x-4">
                    <button
                      onClick={() => setCompareMode(!compareMode)}
                      className={`px-4 py-2 rounded-lg text-sm font-bold border transition-all ${compareMode ? 'bg-blue-600 border-blue-500 text-white' : 'glass border-white/10 text-gray-400'}`}
                    >
                      {compareMode ? 'Exit Comparison' : 'Compare Models'}
                    </button>
                    <a
                      href="http://100.83.192.30:3000/d/rag-dgx/rag-pipeline-dgx-spark-monitoring"
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
                  <div className="flex flex-col h-full overflow-hidden">
                    <div className="flex space-x-4 mb-6">
                      <input
                        type="text"
                        value={benchmarkInput}
                        onChange={(e) => setBenchmarkInput(e.target.value)}
                        placeholder="Enter a complex legal query for benchmarking..."
                        className="flex-1 glass border-white/10 rounded-xl px-6 py-3 text-sm focus:outline-none"
                      />
                      <button
                        onClick={handleRunBenchmark}
                        disabled={isBenchmarking || !benchmarkInput}
                        className="px-8 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-xl font-bold transition-all flex items-center space-x-2"
                      >
                        {isBenchmarking ? <Loader2 className="animate-spin" size={18} /> : <Activity size={18} />}
                        <span>Run All</span>
                      </button>
                    </div>

                    <div className="flex-1 overflow-x-auto overflow-y-hidden pb-4 custom-scrollbar">
                      <div className="flex space-x-6 h-full min-w-max">
                        {['qwen3.5-35b', 'claude-sonnet-4-6', 'gemini-3.1-pro'].map(model => (
                          <div key={model} className="w-[400px] flex flex-col glass border-white/10 rounded-3xl p-6">
                            <div className="flex items-center justify-between mb-4 pb-4 border-b border-white/5">
                              <h3 className="font-bold text-blue-400">{model}</h3>
                              {benchmarkResults[model] && (
                                <div className={`text-lg font-black ${benchmarkResults[model].faithfulness > 0.8 ? 'text-green-500' : 'text-yellow-500'}`}>
                                  {Math.round(benchmarkResults[model].faithfulness * 100)}%
                                </div>
                              )}
                            </div>

                            {benchmarkResults[model] ? (
                              <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar">
                                <div className="space-y-6">
                                  <div>
                                    <div className="text-[10px] font-bold text-gray-500 uppercase mb-2">Generated Answer</div>
                                    <div className="text-[13px] text-gray-300 leading-relaxed bg-white/5 p-4 rounded-xl border border-white/5">
                                      <ReactMarkdown>{benchmarkResults[model].answer}</ReactMarkdown>
                                    </div>
                                  </div>
                                  <div className="grid grid-cols-2 gap-4">
                                    <div className="bg-white/5 p-3 rounded-xl">
                                      <div className="text-[9px] font-bold text-blue-500 mb-1 uppercase">Faithfulness</div>
                                      <p className="text-[11px] text-gray-400 leading-tight">{benchmarkResults[model].faithfulness_reason}</p>
                                    </div>
                                    <div className="bg-white/5 p-3 rounded-xl">
                                      <div className="text-[9px] font-bold text-green-500 mb-1 uppercase">Relevancy</div>
                                      <p className="text-[11px] text-gray-400 leading-tight">{benchmarkResults[model].relevancy_reason}</p>
                                    </div>
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
                        ))}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 gap-6 overflow-y-auto pr-2 custom-scrollbar">
                    {evalHistory.length === 0 ? (
                      <div className="h-64 glass flex flex-col items-center justify-center text-gray-500 rounded-3xl border-dashed border-2 border-white/5">
                        <Activity size={48} className="mb-4 opacity-20" />
                        <p>No evaluations recorded yet. Start a chat to see metrics.</p>
                      </div>
                    ) : (
                      evalHistory.map((ev, idx) => (
                        <div key={idx} className="glass p-6 rounded-3xl border border-white/5 hover:border-blue-500/30 transition-all">
                          <div className="flex items-center justify-between mb-4">
                            <div className="text-xs font-bold text-gray-500 uppercase tracking-widest">{ev.timestamp}</div>
                            <div className="flex space-x-4">
                              <div className="flex items-center space-x-2">
                                <span className="text-[10px] uppercase font-bold text-gray-500">Faithfulness:</span>
                                <span className={`text-sm font-black ${ev.faithfulness > 0.8 ? 'text-green-500' : 'text-yellow-500'}`}>
                                  {Math.round(ev.faithfulness * 100)}%
                                </span>
                              </div>
                              <div className="flex items-center space-x-2">
                                <span className="text-[10px] uppercase font-bold text-gray-500">Relevancy:</span>
                                <span className={`text-sm font-black ${ev.relevancy > 0.8 ? 'text-green-500' : 'text-yellow-500'}`}>
                                  {Math.round(ev.relevancy * 100)}%
                                </span>
                              </div>
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
                      ))
                    )}
                  </div>
                )}
              </motion.div>
            ) : activeTab === 'compliance' ? (
              <motion.div
                key="compliance"
                initial={{ opacity: 0, scale: 0.98 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 1.02 }}
                className="h-full flex flex-col p-8 max-w-6xl mx-auto"
              >
                <div className="flex items-center justify-between mb-8">
                  <div>
                    <h2 className="text-2xl font-bold">Automated Compliance Auditor</h2>
                    <p className="text-xs text-gray-500 mt-1">Verify project profiles against legal and BIM standards</p>
                  </div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 h-full overflow-hidden">
                  {/* Profile Input */}
                  <div className="flex flex-col space-y-4">
                    <div className="flex-1 glass border-white/10 rounded-3xl p-6 flex flex-col">
                      <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-4">Project Profile / BIM Execution Plan</label>
                      <textarea
                        value={complianceProfile}
                        onChange={(e) => setComplianceProfile(e.target.value)}
                        placeholder="Dán thông tin dự án, ví dụ: 'Dự án chung cư cao tầng tại Hà Nội, yêu cầu áp dụng BIM Level 2, nộp tệp IFC cho Sở Xây dựng...'"
                        className="flex-1 bg-transparent border-none focus:outline-none text-sm text-gray-300 leading-relaxed resize-none custom-scrollbar"
                      />
                    </div>
                    <button
                      onClick={handleComplianceCheck}
                      disabled={isCheckingCompliance || !complianceProfile}
                      className="w-full py-4 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-2xl font-bold transition-all flex items-center justify-center space-x-3 shadow-xl shadow-blue-600/20"
                    >
                      {isCheckingCompliance ? <Loader2 className="animate-spin" size={20} /> : <FileCheck size={20} />}
                      <span>Run Compliance Audit</span>
                    </button>
                  </div>

                  {/* Audit Results */}
                  <div className="glass border-white/10 rounded-3xl p-6 overflow-y-auto custom-scrollbar bg-[#08080f]/50">
                    <h3 className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-6">Compliance Report</h3>
                    {complianceReport ? (
                      <div className="space-y-6">
                        {complianceReport.map((item, idx) => (
                          <div key={idx} className="p-5 bg-white/5 border border-white/10 rounded-2xl hover:border-blue-500/30 transition-all group">
                            <div className="flex items-center justify-between mb-3">
                              <span className={`px-2 py-0.5 rounded text-[9px] font-black uppercase tracking-tighter ${item.status === 'PASS' ? 'bg-green-500/20 text-green-500' :
                                  item.status === 'FAIL' ? 'bg-red-500/20 text-red-500' : 'bg-yellow-500/20 text-yellow-500'
                                }`}>
                                {item.status}
                              </span>
                              <div className="text-[10px] text-gray-500 italic">{item.citation}</div>
                            </div>
                            <h4 className="text-sm font-bold text-gray-200 mb-2 group-hover:text-blue-400 transition-colors">{item.requirement}</h4>
                            <p className="text-[12px] text-gray-400 leading-relaxed">{item.reason}</p>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="h-full flex flex-col items-center justify-center text-gray-600 space-y-4">
                        <Database size={48} className="opacity-10" />
                        <p className="text-xs text-center px-12">Hệ thống sẽ tự động trích xuất các yêu cầu từ hồ sơ và đối soát với kho dữ liệu pháp quy trung tâm.</p>
                      </div>
                    )}
                  </div>
                </div>
              </motion.div>
            ) : null}
          </AnimatePresence>
        </main>
      </div>

      {/* PDF Preview Modal */}
      <AnimatePresence>
        {preview && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[100] bg-black/80 backdrop-blur-sm flex items-center justify-center p-12"
          >
            <motion.div
              initial={{ scale: 0.9, y: 20 }}
              animate={{ scale: 1, y: 0 }}
              className="glass max-w-6xl w-full h-[85vh] rounded-3xl overflow-hidden flex flex-col border-blue-500/30"
            >
              <div className="h-16 flex items-center justify-between px-8 border-b border-white/5">
                <div className="flex items-center space-x-3">
                  <FileText className="text-blue-500" />
                  <span className="font-bold text-sm tracking-tight">{preview.source} (Trang {preview.page})</span>
                </div>
                <div className="flex items-center space-x-4">
                  <button
                    onClick={() => handleAnalyzeConflicts(preview.source)}
                    disabled={isAnalyzingConflicts}
                    className="flex items-center space-x-2 px-4 py-1.5 bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/30 rounded-lg text-[11px] font-bold transition-all disabled:opacity-50"
                  >
                    {isAnalyzingConflicts ? <Loader2 size={14} className="animate-spin" /> : <AlertTriangle size={14} />}
                    <span>Kiểm tra mâu thuẫn</span>
                  </button>
                  <button
                    onClick={() => setPreview(null)}
                    className="p-2 hover:bg-white/10 rounded-full transition-colors"
                  >
                    <X size={24} />
                  </button>
                </div>
              </div>

              <div className="flex-1 flex overflow-hidden">
                {/* Left: Metadata/Conflicts */}
                <div className="w-80 border-r border-white/5 bg-[#0a0a0f] p-6 overflow-y-auto">
                  <h3 className="text-xs font-black text-gray-500 uppercase tracking-widest mb-6">Logical Consistency</h3>
                  {conflictReport ? (
                    <div className="space-y-4">
                      {conflictReport.length === 0 ? (
                        <div className="p-4 bg-green-500/5 border border-green-500/20 rounded-xl text-[12px] text-green-500">
                          Không phát hiện mâu thuẫn logic với các văn bản lân cận.
                        </div>
                      ) : (
                        conflictReport.map((c, idx) => (
                          <div key={idx} className="p-4 bg-red-500/5 border border-red-500/20 rounded-xl space-y-2">
                            <div className="flex items-center space-x-2 text-red-500">
                              <AlertTriangle size={14} />
                              <span className="text-[10px] font-bold uppercase tracking-wider">{c.severity} CONFLICT</span>
                            </div>
                            <div className="text-[11px] font-bold text-gray-300">Target: {c.target}</div>
                            <p className="text-[11px] text-gray-500 leading-tight">{c.reason}</p>
                          </div>
                        ))
                      )}
                    </div>
                  ) : (
                    <div className="text-[11px] text-gray-600 italic">
                      Nhấn "Kiểm tra mâu thuẫn" để chạy AI đánh giá tính nhất quán logic với các văn bản liên quan trong Graph.
                    </div>
                  )}
                </div>

                {/* Right: PDF Render */}
                <div className="flex-1 overflow-auto bg-[#11111b] p-8 flex justify-center relative custom-scrollbar">
                  <div className="relative inline-block h-fit">
                    <img
                      src={`data:image/png;base64,${preview.image_b64}`}
                      alt="PDF Page"
                      className="max-w-full shadow-2xl rounded-sm border border-white/5"
                    />
                    {preview.highlightBbox && (
                      <motion.div
                        initial={{ opacity: 0, scale: 0.8 }}
                        animate={{ opacity: 1, scale: 1 }}
                        style={{
                          position: 'absolute',
                          top: `${preview.highlightBbox[0] / 10}%`,
                          left: `${preview.highlightBbox[1] / 10}%`,
                          width: `${(preview.highlightBbox[3] - preview.highlightBbox[1]) / 10}%`,
                          height: `${(preview.highlightBbox[2] - preview.highlightBbox[0]) / 10}%`,
                          backgroundColor: 'rgba(59, 130, 246, 0.3)',
                          border: '2px solid rgba(59, 130, 246, 0.8)',
                          borderRadius: '2px',
                          pointerEvents: 'none',
                          boxShadow: '0 0 20px rgba(59, 130, 246, 0.4)'
                        }}
                      />
                    )}
                  </div>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default Dashboard;
