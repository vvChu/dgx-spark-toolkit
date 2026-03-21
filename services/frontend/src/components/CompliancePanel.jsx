import { FileCheck, Loader2, Database } from 'lucide-react';
import { motion } from 'framer-motion';

export default function CompliancePanel({
  complianceProfile, setComplianceProfile,
  isCheckingCompliance, complianceReport,
  handleComplianceCheck,
}) {
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
              placeholder="Dán thông tin dự án, ví dụ: 'Dự án chung cư cao tầng tại Hà Nội, yêu cầu áp dụng BIM Level 2, nộp tệp IFC cho Sở Xây dựng...'"
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
                Hệ thống sẽ tự động trích xuất các yêu cầu từ hồ sơ và đối soát với kho dữ liệu pháp quy trung tâm.
              </p>
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
}
