/**
 * AI Gateway Client — TypeScript Module
 * Copy file này vào project để dùng ngay.
 *
 * Usage:
 *   import { chat, chatStream, listModels } from './ai-client';
 *
 *   const reply = await chat('Xin chào!');
 *   const reply2 = await chat('Explain REST API', { model: 'claude-sonnet-4-6' });
 *
 *   for await (const chunk of chatStream('Write quicksort')) {
 *     process.stdout.write(chunk);
 *   }
 *
 * Requirements:
 *   npm install openai dotenv
 */

import OpenAI from 'openai';
import 'dotenv/config';

// --- Initialize client ---
export const ai = new OpenAI({
  baseURL: process.env.AI_GATEWAY_URL || 'http://100.83.192.30:8090/v1',
  apiKey: process.env.AI_GATEWAY_KEY || process.env.OPENAI_API_KEY || '',
});

const DEFAULT_MODEL = process.env.AI_MODEL || 'qwen-local-primary';

interface ChatOptions {
  model?: string;
  system?: string;
  maxTokens?: number;
  temperature?: number;
}

/**
 * Send a chat message and get a response string.
 */
export async function chat(
  message: string,
  options: ChatOptions = {},
): Promise<string> {
  const { model = DEFAULT_MODEL, system, maxTokens = 1024, temperature = 0.7 } = options;

  const messages: OpenAI.ChatCompletionMessageParam[] = [];
  if (system) messages.push({ role: 'system', content: system });
  messages.push({ role: 'user', content: message });

  const response = await ai.chat.completions.create({
    model,
    messages,
    max_tokens: maxTokens,
    temperature,
  });

  return response.choices[0].message.content || '';
}

/**
 * Stream a chat response. Yields content strings as they arrive.
 */
export async function* chatStream(
  message: string,
  options: ChatOptions = {},
): AsyncGenerator<string> {
  const { model = DEFAULT_MODEL, system, maxTokens = 1024, temperature = 0.7 } = options;

  const messages: OpenAI.ChatCompletionMessageParam[] = [];
  if (system) messages.push({ role: 'system', content: system });
  messages.push({ role: 'user', content: message });

  const stream = await ai.chat.completions.create({
    model,
    messages,
    max_tokens: maxTokens,
    temperature,
    stream: true,
  });

  for await (const chunk of stream) {
    const content = chunk.choices[0]?.delta?.content;
    if (content) yield content;
  }
}

/**
 * List all available models on the gateway.
 */
export async function listModels(): Promise<string[]> {
  const models = await ai.models.list();
  const ids = new Set<string>();
  for await (const m of models) {
    ids.add(m.id);
  }
  return [...ids].sort();
}

// --- Demo / Self-test ---
if (import.meta.url === `file://${process.argv[1]}`) {
  console.log(`🔌 Gateway: ${ai.baseURL}`);
  console.log(`🤖 Default model: ${DEFAULT_MODEL}`);
  console.log();

  // List models
  const models = await listModels();
  console.log('📋 Available models:');
  for (const m of models) {
    const prefix = ['qwen-local-primary', 'rag-core', 'rag-light'].includes(m) ? '🖥️ ' : '☁️ ';
    console.log(`   ${prefix} ${m}`);
  }

  // Quick chat
  console.log();
  console.log('💬 Chat test:');
  const reply = await chat('Xin chào! Trả lời 1 câu ngắn.', { maxTokens: 50 });
  console.log(`   ${reply}`);

  // Streaming
  console.log();
  console.log('📡 Streaming test:');
  process.stdout.write('   ');
  for await (const chunk of chatStream('Đếm 1-5 bằng tiếng Việt', { maxTokens: 50 })) {
    process.stdout.write(chunk);
  }
  console.log();
}
