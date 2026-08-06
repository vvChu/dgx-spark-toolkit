import { useState, useRef, useEffect, useCallback } from 'react';
import { sendFeedback, type ContextItem } from '../lib/api';
import { StreamClient } from '../lib/streamClient';

export interface Message {
  id: string;
  role: 'user' | 'ai';
  content: string;
  thought?: string;
  context?: ContextItem[];
  feedback?: 'positive' | 'negative';
}

export default function useChat(
  language: string,
  onEvaluate: (query: string, answer: string, context: string[]) => void,
  onDataRefresh: () => void,
) {
  const [messages, setMessages] = useState<Message[]>([
    { id: 'welcome', role: 'ai', content: 'Chao anh, em la Spark BIM Expert. Em da san sang ho tro anh tra cuu va phan tich hon 8.000 van ban phap luat voi cong nghe GraphRAG.' },
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const scrollToBottom = () => chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  useEffect(scrollToBottom, [messages]);

  const handleSendMessage = useCallback(async () => {
    if (!input || isLoading) return;
    const query = input;
    const userMsg: Message = { id: `user-${Date.now()}`, role: 'user', content: query };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setIsLoading(true);

    const aiMsgId = `ai-${Date.now()}`;
    let contextItems: ContextItem[] = [];
    let fullContent = '';
    let fullThought = '';

    try {
      abortRef.current = new AbortController();
      setMessages((prev) => [...prev, { id: aiMsgId, role: 'ai', content: '', thought: '' }]);

      await StreamClient.streamChat({
        query,
        language,
        onContext: (items) => {
          contextItems = items;
        },
        onToken: (token) => {
          fullContent += token;
          setMessages((prev) =>
            prev.map((m) => (m.id === aiMsgId ? { ...m, content: fullContent, thought: fullThought, context: contextItems } : m)),
          );
        },
        onThought: (thought) => {
          fullThought += thought;
          setMessages((prev) =>
            prev.map((m) => (m.id === aiMsgId ? { ...m, thought: fullThought } : m)),
          );
        },
        onError: (errStr) => {
          console.error('Stream error event:', errStr);
        },
        signal: abortRef.current.signal,
      });

      const contextStrs = contextItems.map((c) => c.text);
      onEvaluate(query, fullContent, contextStrs);
      onDataRefresh();
    } catch (err) {
      if ((err as Error).name === 'AbortError') return;
      setMessages((prev) => [...prev, { id: `err-${Date.now()}`, role: 'ai', content: 'Co loi ket noi toi Spark Engine. Anh vui long kiem tra lai dich vu nhe.' }]);
    } finally {
      setIsLoading(false);
      abortRef.current = null;
    }
  }, [input, isLoading, language, onEvaluate, onDataRefresh]);

  const handleFeedback = useCallback(
    async (msgIndex: number, isPositive: boolean) => {
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

  return {
    messages,
    input,
    setInput,
    isLoading,
    chatEndRef,
    handleSendMessage,
    handleFeedback,
  };
}
