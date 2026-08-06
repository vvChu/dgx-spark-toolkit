import { useState, useCallback } from 'react';
import { checkCompliance, analyzeConflicts } from '../lib/api';

export interface ComplianceItem {
  status: 'PASS' | 'FAIL' | 'WARNING';
  citation: string;
  requirement: string;
  reason: string;
}

export interface Conflict {
  severity: string;
  target: string;
  reason: string;
}

export default function useCompliance() {
  const [complianceProfile, setComplianceProfile] = useState('');
  const [complianceReport, setComplianceReport] = useState<ComplianceItem[] | null>(null);
  const [isCheckingCompliance, setIsCheckingCompliance] = useState(false);
  const [isAnalyzingConflicts, setIsAnalyzingConflicts] = useState(false);
  const [conflictReport, setConflictReport] = useState<Conflict[] | null>(null);

  const handleComplianceCheck = useCallback(async () => {
    if (!complianceProfile || isCheckingCompliance) return;
    setIsCheckingCompliance(true);
    try {
      const data = await checkCompliance(complianceProfile);
      setComplianceReport(data.report as unknown as ComplianceItem[]);
    } catch (err) {
      console.error('Compliance check failed:', err);
    } finally {
      setIsCheckingCompliance(false);
    }
  }, [complianceProfile, isCheckingCompliance]);

  const handleAnalyzeConflicts = useCallback(async (docId: string) => {
    setIsAnalyzingConflicts(true);
    setConflictReport(null);
    try {
      const data = await analyzeConflicts(docId);
      setConflictReport(data.conflicts as Conflict[]);
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
