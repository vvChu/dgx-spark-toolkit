import { AnimatePresence } from 'framer-motion';
import useDashboard from './hooks/useDashboard';
import Sidebar from './components/Sidebar';
import Header from './components/Header';
import ChatPanel from './components/ChatPanel';
import GraphPanel from './components/GraphPanel';
import BenchmarkPanel from './components/BenchmarkPanel';
import CompliancePanel from './components/CompliancePanel';
import PreviewModal from './components/PreviewModal';

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
              <GraphPanel
                graphData={d.graphData}
                onNodeClick={d.handleNodeClick}
                onNodeRightClick={d.handleExpandNode}
              />
            )}
            {d.activeTab === 'benchmarking' && (
              <BenchmarkPanel
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
