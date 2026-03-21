import axios from 'axios';

export const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8005';
export const GRAFANA_URL = import.meta.env.VITE_GRAFANA_URL || 'http://localhost:3000';

export const api = axios.create({ baseURL: API_BASE });

export async function fetchStats() {
  const resp = await api.get('/stats');
  return resp.data;
}

export async function fetchGraphData() {
  const resp = await api.get('/graph/data');
  return resp.data;
}

export async function sendChat(query, language, model) {
  const resp = await api.post('/chat', { query, language, ...(model && { model }) });
  return resp.data;
}

export async function evaluateAnswer(query, answer, context) {
  const resp = await api.post('/evaluate', { query, answer, context });
  return resp.data;
}

export async function sendFeedback(query, answer, isPositive) {
  await api.post('/feedback', { query, answer, is_positive: isPositive });
}

export async function fetchPreview(source, page) {
  const resp = await api.get('/preview', { params: { source, page } });
  return resp.data;
}

export async function fetchGraphNeighbors(nodeId) {
  const resp = await api.get(`/graph/neighbors/${encodeURIComponent(nodeId)}`);
  return resp.data;
}

export async function checkCompliance(projectProfile) {
  const resp = await api.post('/analysis/compliance', { project_profile: projectProfile });
  return resp.data;
}

export async function analyzeConflicts(docId) {
  const resp = await api.post('/analysis/conflict', { doc_id: docId });
  return resp.data;
}
