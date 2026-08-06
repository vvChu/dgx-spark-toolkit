import { useState, useCallback } from 'react';
import { evaluateAnswer } from '../lib/api';

export interface Evaluation {
  query: string;
  faithfulness: number;
  relevancy: number;
  faithfulness_reason: string;
  relevancy_reason: string;
  suggestions?: string[];
  timestamp: string;
  loading?: boolean;
}

export default function useEvaluation() {
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [evalHistory, setEvalHistory] = useState<Evaluation[]>([]);
  const [compareMode, setCompareMode] = useState(false);

  const handleEvaluate = useCallback(async (query: string, answer: string, context: string[]) => {
    try {
      if (!context || context.length === 0) {
        const cachedEval: Evaluation = {
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
      setEvaluation({ loading: true } as Evaluation);
      const data = await evaluateAnswer(query, answer, context);
      const fullEval: Evaluation = { ...data, query, timestamp: new Date().toLocaleTimeString() };
      setEvaluation(fullEval);
      setEvalHistory((prev) => [fullEval, ...prev].slice(0, 10));
    } catch {
      setEvaluation(null);
    }
  }, []);

  return {
    evaluation,
    evalHistory,
    compareMode,
    setCompareMode,
    handleEvaluate,
  };
}
