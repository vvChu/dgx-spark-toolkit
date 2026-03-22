import { useState, useEffect, useRef, useCallback } from 'react';
import { fetchStats, fetchGraphData, fetchPreview, fetchGraphNeighbors } from '../lib/api';
import useChat from './useChat';
import useBenchmark from './useBenchmark';
import useCompliance from './useCompliance';
import useEvaluation from './useEvaluation';

export default function useDashboard() {
  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const [activeTab, setActiveTab] = useState('chat');
  const [stats, setStats] = useState({ docs: 0, rels: 0, milvus: 0, total: 8870 });
  const [preview, setPreview] = useState(null);
  const [language, setLanguage] = useState('vi');
  const abortRef = useRef(null);

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

    // Initial fetch + polling interval — the lint rule flags setState in effects
    // but this is the standard pattern for data-fetching effects.
    const doFetch = () => refreshData(controller.signal);
    doFetch();
    const interval = setInterval(() => {
      if (!document.hidden) doFetch();
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

  // Feature hooks
  const evaluation = useEvaluation();
  const chat = useChat(language, evaluation.handleEvaluate, refreshData);
  const benchmark = useBenchmark(language);
  const compliance = useCompliance();

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

  return {
    // Shared state
    graphData, activeTab, stats, preview, language,
    setActiveTab, setPreview, setLanguage,
    handleNodeClick, handleExpandNode,
    // Chat feature
    ...chat,
    // Evaluation feature
    evaluation: evaluation.evaluation,
    evalHistory: evaluation.evalHistory,
    compareMode: evaluation.compareMode,
    setCompareMode: evaluation.setCompareMode,
    // Benchmark feature
    ...benchmark,
    // Compliance feature
    ...compliance,
  };
}
