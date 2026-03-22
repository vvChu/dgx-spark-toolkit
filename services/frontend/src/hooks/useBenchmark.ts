import { useState, useCallback } from 'react';
import { sendChat, evaluateAnswer, EvaluationResponse } from '../lib/api';

export interface BenchmarkResult extends EvaluationResponse {
  answer: string;
}

export default function useBenchmark(language: string) {
  const [benchmarkInput, setBenchmarkInput] = useState('');
  const [isBenchmarking, setIsBenchmarking] = useState(false);
  const [benchmarkResults, setBenchmarkResults] = useState<Record<string, BenchmarkResult>>({});

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

  return {
    benchmarkInput,
    setBenchmarkInput,
    isBenchmarking,
    benchmarkResults,
    handleRunBenchmark,
  };
}
