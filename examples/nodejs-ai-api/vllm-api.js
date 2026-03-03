/**
 * vLLM Node.js API Client
 * OpenAI-compatible API for integrating LLM into Node.js/Express applications
 * 
 * Usage:
 *   const { chat, complete } = require('./vllm-api');
 *   const reply = await chat('Hello!');
 */

const VLLM_URL = process.env.VLLM_API_BASE || 'http://100.83.192.30:8001/v1';
const DEFAULT_MODEL = process.env.VLLM_MODEL || 'qwen3.5-35b';

async function chat(message, model = DEFAULT_MODEL) {
    try {
        const response = await fetch(`${VLLM_URL}/chat/completions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model,
                messages: [{ role: 'user', content: message }],
                temperature: 0.7,
                max_tokens: 1024
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        return data.choices[0].message.content;
    } catch (error) {
        console.error("Error connecting to vLLM:", error.message);
        return null;
    }
}

async function complete(prompt, model = DEFAULT_MODEL) {
    try {
        const response = await fetch(`${VLLM_URL}/completions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model,
                prompt,
                max_tokens: 256,
                temperature: 0.7
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        return data.choices[0].text;
    } catch (error) {
        console.error("Error generating text:", error.message);
        return null;
    }
}

module.exports = { chat, complete };

// Test
if (require.main === module) {
    console.log(`Connecting to vLLM at ${VLLM_URL}...`);
    console.log(`Model: ${DEFAULT_MODEL}`);
    chat('Hello! Tell me about DGX Spark in one sentence.')
        .then(res => console.log("Response:", res));
}
