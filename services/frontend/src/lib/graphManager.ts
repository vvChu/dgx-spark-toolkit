import type { GraphDataResponse, GraphNode } from './api';

export interface RenderNodeOptions {
  fontSize?: number;
  backgroundColor?: string;
  defaultTextColor?: string;
}

export class LegalGraphManager {
  /**
   * Normalize and enhance raw GraphDataResponse for ForceGraph2D rendering.
   */
  static transformGraphData(data: GraphDataResponse | null | undefined): GraphDataResponse {
    if (!data || !Array.isArray(data.nodes)) {
      return { nodes: [], links: [] };
    }
    const nodes = data.nodes.map((node) => ({
      ...node,
      group: node.group || 'document',
      val: node.val || 5,
    }));
    const links = (data.links || []).filter(
      (link) => link.source && link.target
    );
    return { nodes, links };
  }

  /**
   * Decoupled Canvas rendering strategy for graph nodes.
   */
  static renderNodeCanvas(
    node: { x?: number; y?: number; name?: string; color?: string },
    ctx: CanvasRenderingContext2D,
    globalScale: number,
    options: RenderNodeOptions = {}
  ): void {
    if (typeof node.x !== 'number' || typeof node.y !== 'number') return;
    const label = node.name || '';
    const baseFontSize = options.fontSize || 12;
    const fontSize = baseFontSize / globalScale;
    ctx.font = `${fontSize}px Inter, sans-serif`;

    const textWidth = ctx.measureText(label).width;
    const padding = fontSize * 0.2;
    const width = textWidth + padding * 2;
    const height = fontSize + padding * 2;

    ctx.fillStyle = options.backgroundColor || 'rgba(10, 10, 20, 0.85)';
    ctx.fillRect(node.x - width / 2, node.y - height / 2, width, height);

    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = node.color || options.defaultTextColor || '#60a5fa';
    ctx.fillText(label, node.x, node.y);
  }

  /**
   * Find immediate neighbor nodes and connecting links for a target node.
   */
  static findNeighbors(
    data: GraphDataResponse,
    nodeId: string
  ): { neighborNodeIds: Set<string>; links: typeof data.links } {
    const neighborNodeIds = new Set<string>([nodeId]);
    const connectingLinks: typeof data.links = [];

    for (const link of data.links) {
      const sourceId = typeof link.source === 'object' ? (link.source as { id: string }).id : link.source;
      const targetId = typeof link.target === 'object' ? (link.target as { id: string }).id : link.target;

      if (sourceId === nodeId || targetId === nodeId) {
        neighborNodeIds.add(sourceId);
        neighborNodeIds.add(targetId);
        connectingLinks.push(link);
      }
    }

    return { neighborNodeIds, links: connectingLinks };
  }
}
