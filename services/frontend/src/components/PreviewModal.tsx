import { FileText, AlertTriangle, Loader2, X } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import type { PreviewResponse } from '../lib/api';
import type { Conflict } from '../hooks/useCompliance';

interface PreviewWithHighlight extends PreviewResponse {
  highlightBbox?: number[] | null;
  image_b64?: string;
}

interface PreviewModalProps {
  preview: PreviewWithHighlight | null;
  setPreview: (value: PreviewWithHighlight | null) => void;
  conflictReport: Conflict[] | null;
  isAnalyzingConflicts: boolean;
  handleAnalyzeConflicts: (docId: string) => void;
}

export default function PreviewModal({
  preview, setPreview,
  conflictReport, isAnalyzingConflicts, handleAnalyzeConflicts,
}: PreviewModalProps) {
  return (
    <AnimatePresence>
      {preview && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[100] bg-black/80 backdrop-blur-sm flex items-center justify-center p-12"
        >
          <motion.div
            initial={{ scale: 0.9, y: 20 }}
            animate={{ scale: 1, y: 0 }}
            className="glass max-w-6xl w-full h-[85vh] rounded-3xl overflow-hidden flex flex-col border-blue-500/30"
          >
            {/* Modal header */}
            <div className="h-16 flex items-center justify-between px-8 border-b border-white/5">
              <div className="flex items-center space-x-3">
                <FileText className="text-blue-500" />
                <span className="font-bold text-sm tracking-tight">
                  {preview.source} (Trang {preview.page})
                </span>
              </div>
              <div className="flex items-center space-x-4">
                <button
                  onClick={() => handleAnalyzeConflicts(preview.source)}
                  disabled={isAnalyzingConflicts}
                  className="flex items-center space-x-2 px-4 py-1.5 bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/30 rounded-lg text-[11px] font-bold transition-all disabled:opacity-50"
                >
                  {isAnalyzingConflicts ? <Loader2 size={14} className="animate-spin" /> : <AlertTriangle size={14} />}
                  <span>Ki\u1EC3m tra m\u00E2u thu\u1EABn</span>
                </button>
                <button onClick={() => setPreview(null)} className="p-2 hover:bg-white/10 rounded-full transition-colors">
                  <X size={24} />
                </button>
              </div>
            </div>

            <div className="flex-1 flex overflow-hidden">
              {/* Left: Conflicts */}
              <div className="w-80 border-r border-white/5 bg-[#0a0a0f] p-6 overflow-y-auto">
                <h3 className="text-xs font-black text-gray-500 uppercase tracking-widest mb-6">Logical Consistency</h3>
                {conflictReport ? (
                  <ConflictList conflicts={conflictReport} />
                ) : (
                  <div className="text-[11px] text-gray-600 italic">
                    Nh\u1EA5n "Ki\u1EC3m tra m\u00E2u thu\u1EABn" \u0111\u1EC3 ch\u1EA1y AI \u0111\u00E1nh gi\u00E1 t\u00EDnh nh\u1EA5t qu\u00E1n logic v\u1EDBi c\u00E1c v\u0103n b\u1EA3n li\u00EAn quan trong Graph.
                  </div>
                )}
              </div>

              {/* Right: PDF Render */}
              <div className="flex-1 overflow-auto bg-[#11111b] p-8 flex justify-center relative custom-scrollbar">
                <div className="relative inline-block h-fit">
                  <img
                    src={`data:image/png;base64,${preview.image_b64}`}
                    alt="PDF Page"
                    className="max-w-full shadow-2xl rounded-sm border border-white/5"
                  />
                  {preview.highlightBbox && (
                    <motion.div
                      initial={{ opacity: 0, scale: 0.8 }}
                      animate={{ opacity: 1, scale: 1 }}
                      style={{
                        position: 'absolute',
                        top: `${preview.highlightBbox[0] / 10}%`,
                        left: `${preview.highlightBbox[1] / 10}%`,
                        width: `${(preview.highlightBbox[3] - preview.highlightBbox[1]) / 10}%`,
                        height: `${(preview.highlightBbox[2] - preview.highlightBbox[0]) / 10}%`,
                        backgroundColor: 'rgba(59, 130, 246, 0.3)',
                        border: '2px solid rgba(59, 130, 246, 0.8)',
                        borderRadius: '2px',
                        pointerEvents: 'none' as const,
                        boxShadow: '0 0 20px rgba(59, 130, 246, 0.4)',
                      }}
                    />
                  )}
                </div>
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

interface ConflictListProps {
  conflicts: Conflict[];
}

function ConflictList({ conflicts }: ConflictListProps) {
  if (conflicts.length === 0) {
    return (
      <div className="p-4 bg-green-500/5 border border-green-500/20 rounded-xl text-[12px] text-green-500">
        Kh\u00F4ng ph\u00E1t hi\u1EC7n m\u00E2u thu\u1EABn logic v\u1EDBi c\u00E1c v\u0103n b\u1EA3n l\u00E2n c\u1EADn.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {conflicts.map((c, idx) => (
        <div key={idx} className="p-4 bg-red-500/5 border border-red-500/20 rounded-xl space-y-2">
          <div className="flex items-center space-x-2 text-red-500">
            <AlertTriangle size={14} />
            <span className="text-[10px] font-bold uppercase tracking-wider">{c.severity} CONFLICT</span>
          </div>
          <div className="text-[11px] font-bold text-gray-300">Target: {c.target}</div>
          <p className="text-[11px] text-gray-500 leading-tight">{c.reason}</p>
        </div>
      ))}
    </div>
  );
}
