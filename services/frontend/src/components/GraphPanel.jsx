import { motion } from 'framer-motion';
import ForceGraph2D from 'react-force-graph-2d';

export default function GraphPanel({ graphData, onNodeClick, onNodeRightClick }) {
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
          graphData={graphData}
          nodeLabel="name"
          nodeAutoColorBy="group"
          linkDirectionalParticles={2}
          linkDirectionalParticleSpeed={() => 0.005}
          onNodeClick={onNodeClick}
          onNodeRightClick={onNodeRightClick}
          nodeCanvasObject={(node, ctx, globalScale) => {
            const label = node.name;
            const fontSize = 12 / globalScale;
            ctx.font = `${fontSize}px Sans-Serif`;
            const textWidth = ctx.measureText(label).width;
            const bckgDimensions = [textWidth, fontSize].map((n) => n + fontSize * 0.2);

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
          <p>Chưa có dữ liệu đồ thị. Hãy tìm kiếm để xem quan hệ giữa các văn bản.</p>
        </div>
      )}
    </motion.div>
  );
}
