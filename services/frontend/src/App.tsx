import { lazy, Suspense } from 'react';
import { AnimatePresence } from 'framer-motion';
import { Loader2 } from 'lucide-react';
import useDashboard from './hooks/useDashboard';
import Sidebar from './components/Sidebar';
import Header from './components/Header';
import ChatPanel from './components/ChatPanel';
import BenchmarkPanel from './components/BenchmarkPanel';
import CompliancePanel from './components/CompliancePanel';
import PreviewModal from './components/PreviewModal';

const GraphPanel = lazy(() => import('./components/GraphPanel'));

const Dashboard = () => {
  const d = useDashboard();

  return (
    <div className="flex h-screen bg-[#11111b] text-gray-200 overflow-hidden font-sans">
      <Sidebar activeTab={d.activeTab} setActiveTab={d.setActiveTab} />

      <div className="flex-1 flex flex-col relative">
        <Header stats={d.stats} language={d.language} setLanguage={d.setLanguage} />

        <main className="flex-1 overflow-hidden relative" role="main">
          <AnimatePresence mode="wait">
            {d.activeTab === 'chat' && (
              <ChatPanel
                key="chat"
                messages={d.messages}
                input={d.input}
                setInput={d.setInput}
                isLoading={d.isLoading}
                evaluation={d.evaluation}
                handleSendMessage={d.handleSendMessage}
                handleFeedback={d.handleFeedback}
                handleNodeClick={d.handleNodeClick}
                chatEndRef={d.chatEndRef}
              />
            )}
            {d.activeTab === 'graph' && (
              <Suspense
                key="graph"
                fallback={
                  <div
                    role="status"
                    aria-live="polite"
                    className="flex h-full w-full items-center justify-center bg-[#08080f] text-gray-400"
                  >
                    <div className="flex flex-col items-center gap-3">
                      <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
                      <span className="text-sm font-medium">Đang tải đồ thị quan hệ pháp luật...</span>
                    </div>
                  </div>
                }
              >
                <GraphPanel
                  graphData={d.graphData}
                  onNodeClick={d.handleNodeClick}
                  onNodeRightClick={d.handleExpandNode}
                />
              </Suspense>
            )}
            {d.activeTab === 'benchmarking' && (
              <BenchmarkPanel
                key="benchmarking"
                compareMode={d.compareMode}
                setCompareMode={d.setCompareMode}
                benchmarkInput={d.benchmarkInput}
                setBenchmarkInput={d.setBenchmarkInput}
                isBenchmarking={d.isBenchmarking}
                benchmarkResults={d.benchmarkResults}
                evalHistory={d.evalHistory}
                handleRunBenchmark={d.handleRunBenchmark}
              />
            )}
            {d.activeTab === 'compliance' && (
              <CompliancePanel
                key="compliance"
                complianceProfile={d.complianceProfile}
                setComplianceProfile={d.setComplianceProfile}
                isCheckingCompliance={d.isCheckingCompliance}
                complianceReport={d.complianceReport}
                handleComplianceCheck={d.handleComplianceCheck}
              />
            )}
          </AnimatePresence>
        </main>
      </div>

      <PreviewModal
        preview={d.preview}
        setPreview={d.setPreview}
        conflictReport={d.conflictReport}
        isAnalyzingConflicts={d.isAnalyzingConflicts}
        handleAnalyzeConflicts={d.handleAnalyzeConflicts}
      />
    </div>
  );
};

export default Dashboard;
