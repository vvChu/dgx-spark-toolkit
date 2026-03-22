import { motion } from 'framer-motion';
import type { Evaluation } from '../hooks/useEvaluation';

interface EvalBadgeProps {
  evaluation: Evaluation | null;
}

export default function EvalBadge({ evaluation }: EvalBadgeProps) {
  if (!evaluation) return null;

  return (
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
  );
}
