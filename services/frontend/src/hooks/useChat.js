import { useState, useRef, useEffect, useCallback } from 'react';
import { sendChat, sendFeedback } from '../lib/api';

export default function useChat(language, onEvaluate, onDataRefresh) {
  const [messages, setMessages] = useState([
    { id: 'welcome', role: 'ai', content: 'Chào anh, em là Spark BIM Expert. Em đã sẵn sàng hỗ trợ anh tra cứu và phân tích hơn 8.000 văn bản pháp luật với công nghệ GraphRAG.' },
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const chatEndRef = useRef(null);

  const scrollToBottom = () => chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  useEffect(scrollToBottom, [messages]);

  const handleSendMessage = useCallback(async () => {
    if (!input || isLoading) return;
    const userMsg = { id: `user-${Date.now()}`, role: 'user', content: input };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setIsLoading(true);

    try {
      const data = await sendChat(input, language);
      const aiMsg = { id: `ai-${Date.now()}`, role: 'ai', content: data.answer, thought: data.thought, context: data.context };
      setMessages((prev) => [...prev, aiMsg]);
      const contextStrs = data.context ? data.context.map((c) => c.text) : [];
      onEvaluate(input, data.answer, contextStrs);
      onDataRefresh();
    } catch {
      setMessages((prev) => [...prev, { id: `err-${Date.now()}`, role: 'ai', content: 'Có lỗi kết nối tới Spark Engine. Anh vui lòng kiểm tra lại dịch vụ nhé.' }]);
    } finally {
      setIsLoading(false);
    }
  }, [input, isLoading, language, onEvaluate, onDataRefresh]);

  const handleFeedback = useCallback(
    async (msgIndex, isPositive) => {
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
