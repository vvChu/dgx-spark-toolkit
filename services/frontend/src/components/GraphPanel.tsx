import { motion } from 'framer-motion';
import ForceGraph2D from 'react-force-graph-2d';
import type { GraphDataResponse, GraphNode } from '../lib/api';
import { LegalGraphManager } from '../lib/graphManager';

interface GraphPanelProps {
  graphData: GraphDataResponse;
  onNodeClick: (node: GraphNode, bbox?: number[] | null) => void;
  onNodeRightClick: (node: GraphNode) => void;
}

/* eslint-disable @typescript-eslint/no-explicit-any */
export default function GraphPanel({ graphData, onNodeClick, onNodeRightClick }: GraphPanelProps) {
  const transformedData = LegalGraphManager.transformGraphData(graphData);
  const hasNodes = transformedData.nodes.length > 0;

  return (
    <motion.div
      key="graph"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="h-full w-full bg-[#08080f]"
    >
      {hasNodes ? (
        <ForceGraph2D
          graphData={transformedData as any}
          nodeLabel="name"
          nodeAutoColorBy="group"
          linkDirectionalParticles={2}
          linkDirectionalParticleSpeed={() => 0.005}
          onNodeClick={onNodeClick as any}
          onNodeRightClick={onNodeRightClick as any}
          nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
            LegalGraphManager.renderNodeCanvas(node, ctx, globalScale);
          }}
        />
      ) : (
        <div className="flex h-full items-center justify-center text-gray-500">
          <p>Chưa có dữ liệu đồ thị. Hãy tìm kiếm để xem quan hệ giữa các văn bản.</p>
        </div>
      )}
    </motion.div>
  );
}
