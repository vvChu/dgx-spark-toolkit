import { useState, useRef, useEffect, useCallback } from 'react';
import { sendChat, sendFeedback, ContextItem } from '../lib/api';

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

  const scrollToBottom = () => chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  useEffect(scrollToBottom, [messages]);

  const handleSendMessage = useCallback(async () => {
    if (!input || isLoading) return;
    const userMsg: Message = { id: `user-${Date.now()}`, role: 'user', content: input };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setIsLoading(true);

    try {
      const data = await sendChat(input, language);
      const aiMsg: Message = { id: `ai-${Date.now()}`, role: 'ai', content: data.answer, thought: data.thought, context: data.context };
      setMessages((prev) => [...prev, aiMsg]);
      const contextStrs = data.context ? data.context.map((c) => c.text) : [];
      onEvaluate(input, data.answer, contextStrs);
      onDataRefresh();
    } catch {
      setMessages((prev) => [...prev, { id: `err-${Date.now()}`, role: 'ai', content: 'Co loi ket noi toi Spark Engine. Anh vui long kiem tra lai dich vu nhe.' }]);
    } finally {
      setIsLoading(false);
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
