'use client';

import React from 'react';
import UnifiedSettingsModal, { SettingsTabId } from './UnifiedSettingsModal';
import type { DepartmentItem, AdvancedSettingsBundle } from '@/lib/types';
import { getStoredGeminiApiKey, setStoredGeminiApiKey } from '@/lib/api';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialTab?: SettingsTabId;
  userId: string;
  onUpdateUserId: (id: string) => void;
  clearanceLevel: string;
  onUpdateClearanceLevel: (lvl: string) => void;
  departmentId: string;
  onUpdateDepartmentId: (dept: string) => void;
  departments: DepartmentItem[];
  sessionId?: string | null;
  onSettingsChange?: (bundle: AdvancedSettingsBundle) => void;
  geminiApiKey?: string | null;
  onUpdateGeminiApiKey?: (key: string | null) => void;
}

export default function SettingsModal({
  isOpen,
  onClose,
  initialTab = 'general',
  userId,
  onUpdateUserId,
  clearanceLevel,
  onUpdateClearanceLevel,
  departmentId,
  onUpdateDepartmentId,
  departments,
  sessionId,
  onSettingsChange,
  geminiApiKey,
  onUpdateGeminiApiKey,
}: SettingsModalProps) {
  const [apiKey, setApiKey] = React.useState<string | null>(geminiApiKey || getStoredGeminiApiKey());

  const handleUpdateKey = (key: string | null) => {
    setApiKey(key);
    if (key) {
      setStoredGeminiApiKey(key);
    }
    onUpdateGeminiApiKey?.(key);
  };

  return (
    <UnifiedSettingsModal
      isOpen={isOpen}
      onClose={onClose}
      initialTab={initialTab}
      userId={userId}
      onUpdateUserId={onUpdateUserId}
      clearanceLevel={clearanceLevel}
      onUpdateClearanceLevel={onUpdateClearanceLevel}
      departmentId={departmentId}
      onUpdateDepartmentId={onUpdateDepartmentId}
      departments={departments}
      sessionId={sessionId}
      onSettingsChange={onSettingsChange}
      geminiApiKey={apiKey}
      onUpdateGeminiApiKey={handleUpdateKey}
    />
  );
}
