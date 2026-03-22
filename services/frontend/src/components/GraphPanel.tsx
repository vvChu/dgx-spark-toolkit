import { motion } from 'framer-motion';
import ForceGraph2D from 'react-force-graph-2d';
import type { GraphDataResponse, GraphNode } from '../lib/api';

interface GraphPanelProps {
  graphData: GraphDataResponse;
  onNodeClick: (node: GraphNode, bbox?: number[] | null) => void;
  onNodeRightClick: (node: GraphNode) => void;
}

/* eslint-disable @typescript-eslint/no-explicit-any */
export default function GraphPanel({ graphData, onNodeClick, onNodeRightClick }: GraphPanelProps) {
  const hasNodes = graphData?.nodes?.length > 0;

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
          graphData={graphData as any}
          nodeLabel="name"
          nodeAutoColorBy="group"
          linkDirectionalParticles={2}
          linkDirectionalParticleSpeed={() => 0.005}
          onNodeClick={onNodeClick as any}
          onNodeRightClick={onNodeRightClick as any}
          nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
            const label = node.name;
            const fontSize = 12 / globalScale;
            ctx.font = `${fontSize}px Sans-Serif`;
            const textWidth = ctx.measureText(label).width;
            const bckgDimensions = [textWidth, fontSize].map((n: number) => n + fontSize * 0.2);

            ctx.fillStyle = 'rgba(10, 10, 20, 0.8)';
            ctx.fillRect(node.x - bckgDimensions[0] / 2, node.y - bckgDimensions[1] / 2, ...bckgDimensions);

            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillStyle = node.color;
            ctx.fillText(label, node.x, node.y);
          }}
        />
      ) : (
        <div className="flex h-full items-center justify-center text-gray-500">
          <p>Ch\u01B0a c\u00F3 d\u1EEF li\u1EC7u \u0111\u1ED3 th\u1ECB. H\u00E3y t\u00ECm ki\u1EBFm \u0111\u1EC3 xem quan h\u1EC7 gi\u1EEFa c\u00E1c v\u0103n b\u1EA3n.</p>
        </div>
      )}
    </motion.div>
  );
}
