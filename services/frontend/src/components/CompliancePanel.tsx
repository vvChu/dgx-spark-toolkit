import { FileCheck, Loader2, Database } from 'lucide-react';
import { motion } from 'framer-motion';
import type { ComplianceItem } from '../hooks/useCompliance';

interface CompliancePanelProps {
  complianceProfile: string;
  setComplianceProfile: (value: string) => void;
  isCheckingCompliance: boolean;
  complianceReport: ComplianceItem[] | null;
  handleComplianceCheck: () => void;
}

export default function CompliancePanel({
  complianceProfile, setComplianceProfile,
  isCheckingCompliance, complianceReport,
  handleComplianceCheck,
}: CompliancePanelProps) {
  return (
    <motion.div
      key="compliance"
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 1.02 }}
      className="h-full flex flex-col p-8 max-w-6xl mx-auto"
    >
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-2xl font-bold">Automated Compliance Auditor</h2>
          <p className="text-xs text-gray-500 mt-1">Verify project profiles against legal and BIM standards</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 h-full overflow-hidden">
        {/* Profile Input */}
        <div className="flex flex-col space-y-4">
          <div className="flex-1 glass border-white/10 rounded-3xl p-6 flex flex-col">
            <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-4">
              Project Profile / BIM Execution Plan
            </label>
            <textarea
              value={complianceProfile}
              onChange={(e) => setComplianceProfile(e.target.value)}
              placeholder="D\u00E1n th\u00F4ng tin d\u1EF1 \u00E1n, v\u00ED d\u1EE5: 'D\u1EF1 \u00E1n chung c\u01B0 cao t\u1EA7ng t\u1EA1i H\u00E0 N\u1ED9i, y\u00EAu c\u1EA7u \u00E1p d\u1EE5ng BIM Level 2, n\u1ED9p t\u1EC7p IFC cho S\u1EDF X\u00E2y d\u1EF1ng...'"
              className="flex-1 bg-transparent border-none focus:outline-none text-sm text-gray-300 leading-relaxed resize-none custom-scrollbar"
            />
          </div>
          <button
            onClick={handleComplianceCheck}
            disabled={isCheckingCompliance || !complianceProfile}
            className="w-full py-4 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-2xl font-bold transition-all flex items-center justify-center space-x-3 shadow-xl shadow-blue-600/20"
          >
            {isCheckingCompliance ? <Loader2 className="animate-spin" size={20} /> : <FileCheck size={20} />}
            <span>Run Compliance Audit</span>
          </button>
        </div>

        {/* Audit Results */}
        <div className="glass border-white/10 rounded-3xl p-6 overflow-y-auto custom-scrollbar bg-[#08080f]/50">
          <h3 className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-6">Compliance Report</h3>
          {complianceReport ? (
            <div className="space-y-6">
              {complianceReport.map((item, idx) => (
                <div key={idx} className="p-5 bg-white/5 border border-white/10 rounded-2xl hover:border-blue-500/30 transition-all group">
                  <div className="flex items-center justify-between mb-3">
                    <span
                      className={`px-2 py-0.5 rounded text-[9px] font-black uppercase tracking-tighter ${
                        item.status === 'PASS'
                          ? 'bg-green-500/20 text-green-500'
                          : item.status === 'FAIL'
                            ? 'bg-red-500/20 text-red-500'
                            : 'bg-yellow-500/20 text-yellow-500'
                      }`}
                    >
                      {item.status}
                    </span>
                    <div className="text-[10px] text-gray-500 italic">{item.citation}</div>
                  </div>
                  <h4 className="text-sm font-bold text-gray-200 mb-2 group-hover:text-blue-400 transition-colors">
                    {item.requirement}
                  </h4>
                  <p className="text-[12px] text-gray-400 leading-relaxed">{item.reason}</p>
                </div>
              ))}
            </div>
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-gray-600 space-y-4">
              <Database size={48} className="opacity-10" />
              <p className="text-xs text-center px-12">
                H\u1EC7 th\u1ED1ng s\u1EBD t\u1EF1 \u0111\u1ED9ng tr\u00EDch xu\u1EA5t c\u00E1c y\u00EAu c\u1EA7u t\u1EEB h\u1ED3 s\u01A1 v\u00E0 \u0111\u1ED1i so\u00E1t v\u1EDBi kho d\u1EEF li\u1EC7u ph\u00E1p quy trung t\u00E2m.
              </p>
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
}
