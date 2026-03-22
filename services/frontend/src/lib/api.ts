import axios, { AxiosInstance } from 'axios';

export const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8005';
export const GRAFANA_URL = import.meta.env.VITE_GRAFANA_URL || 'http://localhost:3000';

export const api: AxiosInstance = axios.create({ baseURL: API_BASE });

// Response interfaces
export interface StatsResponse {
  neo4j_docs: number;
  neo4j_rels: number;
  milvus_entities: number;
  total_target?: number;
}

export interface GraphNode {
  id: string;
  label?: string;
  page?: number;
  [key: string]: unknown;
}

export interface GraphLink {
  source: string;
  target: string;
  type?: string;
  [key: string]: unknown;
}

export interface GraphDataResponse {
  nodes: GraphNode[];
  links: GraphLink[];
}

export interface ContextItem {
  source: string;
  page: number;
  text: string;
  bbox?: number[];
}

export interface ChatResponse {
  answer: string;
  thought?: string;
  context?: ContextItem[];
}

export interface EvaluationResponse {
  faithfulness: number;
  relevancy: number;
  faithfulness_reason: string;
  relevancy_reason: string;
  suggestions?: string[];
}

export interface PreviewResponse {
  source: string;
  page: number;
  image_url?: string;
  text?: string;
  highlightBbox?: number[] | null;
}

export interface ComplianceResponse {
  report: string;
}

export interface ConflictResponse {
  conflicts: unknown[];
}

// API functions
export async function fetchStats({ signal }: { signal?: AbortSignal } = {}): Promise<StatsResponse> {
  const resp = await api.get<StatsResponse>('/stats', { signal });
  return resp.data;
}

export async function fetchGraphData({ signal }: { signal?: AbortSignal } = {}): Promise<GraphDataResponse> {
  const resp = await api.get<GraphDataResponse>('/graph/data', { signal });
  return resp.data;
}

export async function sendChat(query: string, language: string, model?: string): Promise<ChatResponse> {
  const resp = await api.post<ChatResponse>('/chat', { query, language, ...(model && { model }) });
  return resp.data;
}

export async function evaluateAnswer(query: string, answer: string, context: string[]): Promise<EvaluationResponse> {
  const resp = await api.post<EvaluationResponse>('/evaluate', { query, answer, context });
  return resp.data;
}

export async function sendFeedback(query: string, answer: string, isPositive: boolean): Promise<void> {
  await api.post('/feedback', { query, answer, is_positive: isPositive });
}

export async function fetchPreview(source: string, page: number): Promise<PreviewResponse> {
  const resp = await api.get<PreviewResponse>('/preview', { params: { source, page } });
  return resp.data;
}

export async function fetchGraphNeighbors(nodeId: string): Promise<GraphDataResponse> {
  const resp = await api.get<GraphDataResponse>(`/graph/neighbors/${encodeURIComponent(nodeId)}`);
  return resp.data;
}

export async function checkCompliance(projectProfile: string): Promise<ComplianceResponse> {
  const resp = await api.post<ComplianceResponse>('/analysis/compliance', { project_profile: projectProfile });
  return resp.data;
}

export async function analyzeConflicts(docId: string): Promise<ConflictResponse> {
  const resp = await api.post<ConflictResponse>('/analysis/conflict', { doc_id: docId });
  return resp.data;
}
