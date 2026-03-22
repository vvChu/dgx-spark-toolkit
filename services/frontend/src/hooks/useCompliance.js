import { useState, useCallback } from 'react';
import { checkCompliance, analyzeConflicts } from '../lib/api';

export default function useCompliance() {
  const [complianceProfile, setComplianceProfile] = useState('');
  const [complianceReport, setComplianceReport] = useState(null);
  const [isCheckingCompliance, setIsCheckingCompliance] = useState(false);
  const [isAnalyzingConflicts, setIsAnalyzingConflicts] = useState(false);
  const [conflictReport, setConflictReport] = useState(null);

  const handleComplianceCheck = useCallback(async () => {
    if (!complianceProfile || isCheckingCompliance) return;
    setIsCheckingCompliance(true);
    try {
      const data = await checkCompliance(complianceProfile);
      setComplianceReport(data.report);
    } catch (err) {
      console.error('Compliance check failed:', err);
    } finally {
      setIsCheckingCompliance(false);
    }
  }, [complianceProfile, isCheckingCompliance]);

  const handleAnalyzeConflicts = useCallback(async (docId) => {
    setIsAnalyzingConflicts(true);
    setConflictReport(null);
    try {
      const data = await analyzeConflicts(docId);
      setConflictReport(data.conflicts);
    } catch (err) {
      console.error('Conflict analysis failed:', err);
    } finally {
      setIsAnalyzingConflicts(false);
    }
  }, []);

  return {
    complianceProfile,
    setComplianceProfile,
    complianceReport,
    isCheckingCompliance,
    isAnalyzingConflicts,
    conflictReport,
    handleComplianceCheck,
    handleAnalyzeConflicts,
  };
}
