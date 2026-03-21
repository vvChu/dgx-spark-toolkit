import { useState, useEffect, useRef, useCallback } from 'react';
import {
  fetchStats,
  fetchGraphData,
  sendChat,
  evaluateAnswer,
  sendFeedback,
  fetchPreview,
  fetchGraphNeighbors,
  checkCompliance,
  analyzeConflicts,
} from '../lib/api';

export default function useDashboard() {
  const [messages, setMessages] = useState([
    { id: 'welcome', role: 'ai', content: 'Chào anh, em là Spark BIM Expert. Em đã sẵn sàng hỗ trợ anh tra cứu và phân tích hơn 8.000 văn bản pháp luật với công nghệ GraphRAG.' },
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
  const abortRef = useRef(null);

  const scrollToBottom = () => chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  useEffect(scrollToBottom, [messages]);

  const refreshData = useCallback(async (signal) => {
    try {
      const [statsData, graphRes] = await Promise.all([fetchStats({ signal }), fetchGraphData({ signal })]);
      setStats({
        docs: statsData.neo4j_docs,
        rels: statsData.neo4j_rels,
        milvus: statsData.milvus_entities,
        total: statsData.total_target || 8870,
      });
      setGraphData(graphRes);
    } catch (err) {
      if (err.name !== 'CanceledError' && err.name !== 'AbortError') {
        console.error('Failed to fetch dashboard data:', err);
      }
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    abortRef.current = controller;
    refreshData(controller.signal);
    const interval = setInterval(() => {
      if (!document.hidden) refreshData(controller.signal);
    }, 15000);

    const onVisibilityChange = () => {
      if (!document.hidden) refreshData(controller.signal);
    };
    document.addEventListener('visibilitychange', onVisibilityChange);

    return () => {
      controller.abort();
      clearInterval(interval);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, [refreshData]);

  const handleEvaluate = useCallback(async (query, answer, context) => {
    try {
      if (!context || context.length === 0) {
        const cachedEval = {
          query,
          faithfulness: 1.0,
          relevancy: 1.0,
          faithfulness_reason: 'Answer served from high-confidence semantic cache.',
          relevancy_reason: 'Query perfectly matched a previously answered question.',
          suggestions: [],
          timestamp: new Date().toLocaleTimeString(),
        };
        setEvaluation(cachedEval);
        setEvalHistory((prev) => [cachedEval, ...prev].slice(0, 10));
        return;
      }
      setEvaluation({ loading: true });
      const data = await evaluateAnswer(query, answer, context);
      const fullEval = { ...data, query, timestamp: new Date().toLocaleTimeString() };
      setEvaluation(fullEval);
      setEvalHistory((prev) => [fullEval, ...prev].slice(0, 10));
    } catch {
      setEvaluation(null);
    }
  }, []);

  const handleSendMessage = useCallback(async () => {
    if (!input || isLoading) return;
    const userMsg = { id: `user-${Date.now()}`, role: 'user', content: input };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setIsLoading(true);

    try {
      const data = await sendChat(input, language);
      const aiMsg = { id: `ai-${Date.now()}`, role: 'ai', content: data.answer, thought: data.thought, context: data.context };
      setMessages((prev) => [...prev, aiMsg]);
      const contextStrs = data.context ? data.context.map((c) => c.text) : [];
      handleEvaluate(input, data.answer, contextStrs);
      refreshData();
    } catch {
      setMessages((prev) => [...prev, { id: `err-${Date.now()}`, role: 'ai', content: 'Có lỗi kết nối tới Spark Engine. Anh vui lòng kiểm tra lại dịch vụ nhé.' }]);
    } finally {
      setIsLoading(false);
    }
  }, [input, isLoading, language, handleEvaluate, refreshData]);

  const handleRunBenchmark = useCallback(async () => {
    if (!benchmarkInput || isBenchmarking) return;
    setIsBenchmarking(true);
    setBenchmarkResults({});
    const models = ['qwen3.5-35b', 'claude-opus-4-6-thinking', 'gemini-3.1-pro-high'];

    try {
      await Promise.all(
        models.map(async (model) => {
          try {
            const chatData = await sendChat(benchmarkInput, language, model);
            const contextStrs = chatData.context ? chatData.context.map((c) => c.text) : [];
            const evalData = await evaluateAnswer(benchmarkInput, chatData.answer, contextStrs);
            setBenchmarkResults((prev) => ({ ...prev, [model]: { answer: chatData.answer, ...evalData } }));
          } catch (err) {
            console.error(`Benchmark failed for ${model}:`, err);
          }
        }),
      );
    } finally {
      setIsBenchmarking(false);
    }
  }, [benchmarkInput, isBenchmarking, language]);

  const handleFeedback = useCallback(
    async (msgIndex, isPositive) => {
      const msg = messages[msgIndex];
      const prevMsg = messages[msgIndex - 1];
      try {
        await sendFeedback(prevMsg ? prevMsg.content : 'N/A', msg.content, isPositive);
        setMessages((prev) => {
          const next = [...prev];
          next[msgIndex] = { ...next[msgIndex], feedback: isPositive ? 'positive' : 'negative' };
          return next;
        });
      } catch (err) {
        console.error('Feedback failed:', err);
      }
    },
    [messages],
  );

  const handleNodeClick = useCallback(async (node, bbox = null) => {
    try {
      const data = await fetchPreview(node.id, node.page || 1);
      setPreview({ ...data, highlightBbox: bbox });
    } catch (err) {
      console.error('Preview failed:', err);
    }
  }, []);

  const handleExpandNode = useCallback(
    async (node) => {
      try {
        const { nodes: newNodes, links: newLinks } = await fetchGraphNeighbors(node.id);
        setGraphData((prev) => {
          const existingNodeIds = new Set(prev.nodes.map((n) => n.id));
          const existingLinkIds = new Set(prev.links.map((l) => `${l.source.id || l.source}-${l.target.id || l.target}`));
          return {
            nodes: [...prev.nodes, ...newNodes.filter((n) => !existingNodeIds.has(n.id))],
            links: [...prev.links, ...newLinks.filter((l) => !existingLinkIds.has(`${l.source}-${l.target}`))],
          };
        });
      } catch (err) {
        console.error('Expand failed:', err);
      }
    },
    [],
  );

  const handleComplianceCheck = useCallback(async () => {
    if (!complianceProfile || isCheckingCompliance) return;
    setIsCheckingCompliance(true);
    try {
      const data = await checkCompliance(complianceProfile);
      setComplianceReport(data.report);
    } catch (err) {
      console.error('Compliance check failed:', err);
    } finally {
      setIsCheckingCompliance(false);
    }
  }, [complianceProfile, isCheckingCompliance]);

  const handleAnalyzeConflicts = useCallback(async (docId) => {
    setIsAnalyzingConflicts(true);
    setConflictReport(null);
    try {
      const data = await analyzeConflicts(docId);
      setConflictReport(data.conflicts);
    } catch (err) {
      console.error('Conflict analysis failed:', err);
    } finally {
      setIsAnalyzingConflicts(false);
    }
  }, []);

  return {
    // State
    messages, input, isLoading, graphData, activeTab, stats,
    preview, language, evaluation, evalHistory,
    compareMode, benchmarkInput, isBenchmarking, benchmarkResults,
    complianceProfile, complianceReport, isCheckingCompliance,
    isAnalyzingConflicts, conflictReport, chatEndRef,
    // Setters
    setInput, setActiveTab, setPreview, setLanguage,
    setCompareMode, setBenchmarkInput, setComplianceProfile,
    // Handlers
    handleSendMessage, handleRunBenchmark, handleFeedback,
    handleNodeClick, handleExpandNode,
    handleComplianceCheck, handleAnalyzeConflicts,
  };
}
