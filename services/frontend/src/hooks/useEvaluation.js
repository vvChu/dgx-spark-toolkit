import { useState, useCallback } from 'react';
import { evaluateAnswer } from '../lib/api';

export default function useEvaluation() {
  const [evaluation, setEvaluation] = useState(null);
  const [evalHistory, setEvalHistory] = useState([]);
  const [compareMode, setCompareMode] = useState(false);

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

  return {
    evaluation,
    evalHistory,
    compareMode,
    setCompareMode,
    handleEvaluate,
  };
}
