import { useState, useEffect, useRef, useCallback } from 'react';
import { fetchStats, fetchGraphData, fetchPreview, fetchGraphNeighbors, GraphDataResponse, PreviewResponse, GraphNode } from '../lib/api';
import useChat from './useChat';
import useBenchmark from './useBenchmark';
import useCompliance from './useCompliance';
import useEvaluation from './useEvaluation';

interface Stats {
  docs: number;
  rels: number;
  milvus: number;
  total: number;
}

export default function useDashboard() {
  const [graphData, setGraphData] = useState<GraphDataResponse>({ nodes: [], links: [] });
  const [activeTab, setActiveTab] = useState('chat');
  const [stats, setStats] = useState<Stats>({ docs: 0, rels: 0, milvus: 0, total: 8870 });
  const [preview, setPreview] = useState<(PreviewResponse & { highlightBbox?: number[] | null }) | null>(null);
  const [language, setLanguage] = useState('vi');
  const abortRef = useRef<AbortController | null>(null);

  const refreshData = useCallback(async (signal?: AbortSignal) => {
    try {
      const [statsData, graphRes] = await Promise.all([fetchStats({ signal }), fetchGraphData({ signal })]);
      setStats({
        docs: statsData.neo4j_docs,
        rels: statsData.neo4j_rels,
        milvus: statsData.milvus_entities,
        total: statsData.total_target || 8870,
      });
      setGraphData(graphRes);
    } catch (err: unknown) {
      const error = err as Error;
      if (error.name !== 'CanceledError' && error.name !== 'AbortError') {
        console.error('Failed to fetch dashboard data:', err);
      }
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    abortRef.current = controller;

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

  const handleNodeClick = useCallback(async (node: GraphNode, bbox: number[] | null = null) => {
    try {
      const data = await fetchPreview(node.id, (node.page as number) || 1);
      setPreview({ ...data, highlightBbox: bbox });
    } catch (err) {
      console.error('Preview failed:', err);
    }
  }, []);

  const handleExpandNode = useCallback(
    async (node: GraphNode) => {
      try {
        const { nodes: newNodes, links: newLinks } = await fetchGraphNeighbors(node.id);
        setGraphData((prev) => {
          const existingNodeIds = new Set(prev.nodes.map((n) => n.id));
          const existingLinkIds = new Set(prev.links.map((l) => {
            const src = typeof l.source === 'object' ? (l.source as GraphNode).id : l.source;
            const tgt = typeof l.target === 'object' ? (l.target as GraphNode).id : l.target;
            return `${src}-${tgt}`;
          }));
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
    graphData, activeTab, stats, preview, language,
    setActiveTab, setPreview, setLanguage,
    handleNodeClick, handleExpandNode,
    ...chat,
    evaluation: evaluation.evaluation,
    evalHistory: evaluation.evalHistory,
    compareMode: evaluation.compareMode,
    setCompareMode: evaluation.setCompareMode,
    ...benchmark,
    ...compliance,
  };
}
