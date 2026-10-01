'use client';
import { useState } from 'react';
import { analysisApi, assessApi, llmApi, queryApi } from '@/lib/api';
import { getErrorMessage } from '@/lib/errorMessages';
import { useNotifications } from '@/components/NotificationProvider';
import type { Entity, GraphStats } from '../types';

interface AiActionSources {
  activeProject: { id: string } | null;
  selectedEntity: Entity | null;
  multiSelected: Entity[];
  stats: GraphStats | null;
  /** Where results go: the page's AI Result panel, which renders them as analysis. */
  setAiResult: (result: string | null) => void;
}

/**
 * The AI actions on the selected entity (assessment, gap analysis, competing
 * hypotheses) and the assessment modal over the multi-selection. Results go to
 * `setAiResult`, whose panel renders them as analysis, so a failure is only
 * ever reported by notification and never written there.
 */
export function useAiActions({ activeProject, selectedEntity, multiSelected, stats, setAiResult }: AiActionSources) {
  const { addNotification, updateNotification } = useNotifications();
  const [aiLoading, setAiLoading] = useState(false);
  const [assessModalOpen, setAssessModalOpen] = useState(false);
  const [assessJudgment, setAssessJudgment] = useState('');
  const [assessProbability, setAssessProbability] = useState(0.5);
  const [assessAnalyst, setAssessAnalyst] = useState('');
  const [assessLoading, setAssessLoading] = useState(false);

  async function submitAssessment() {
    if (!activeProject || !assessJudgment.trim()) return;
    setAssessLoading(true);
    try {
      if (multiSelected.length === 1) {
        await assessApi.create(multiSelected[0].id, {
          entity_id: multiSelected[0].id,
          project_id: activeProject.id,
          judgment: assessJudgment,
          probability: assessProbability,
          analyst: assessAnalyst || undefined,
        });
      } else if (multiSelected.length > 1) {
        await assessApi.multi({
          entity_ids: multiSelected.map(e => e.id),
          project_id: activeProject.id,
          judgment: assessJudgment,
          probability: assessProbability,
        });
      }
      setAssessModalOpen(false);
      setAssessJudgment('');
      setAssessProbability(0.5);
      setAssessAnalyst('');
      setAiResult('Assessment submitted successfully.');
    } catch {
      setAiResult('Failed to submit assessment.');
    } finally {
      setAssessLoading(false);
    }
  }

  async function generateAssessment() {
    if (!selectedEntity || !activeProject) return;
    setAiLoading(true);
    const notifId = addNotification({
      type: 'processing',
      title: 'Generating Assessment',
      message: `Analyzing ${selectedEntity.name}...`,
    });
    try {
      const res = await assessApi.generate(selectedEntity.id, {
        entity_id: selectedEntity.id,
        project_id: activeProject.id,
        judgment: '',
        probability: 0.5,
      });
      // The backend returns a 200 {error: ...} envelope on failure; treat it as
      // one instead of rendering the error string as if it were the assessment.
      if (res.data.error) {
        updateNotification(notifId, {
          type: 'error',
          title: 'Assessment Failed',
          message: `Could not assess ${selectedEntity.name} — check LLM configuration.`,
        });
        return;
      }
      setAiResult(res.data.assessment);
      updateNotification(notifId, {
        type: 'success',
        title: 'Assessment Ready',
        message: `Assessment for ${selectedEntity.name} complete.`,
      });
    } catch {
      // Includes the 503 the route raises when no model can run. Reported by
      // the notification only — aiResult renders as if it were analysis.
      updateNotification(notifId, {
        type: 'error',
        title: 'Assessment Failed',
        message: `Failed to generate assessment for ${selectedEntity.name}.`,
      });
    } finally {
      setAiLoading(false);
    }
  }

  async function generateAssessmentFromModal() {
    if (!activeProject || multiSelected.length === 0) return;
    setAssessLoading(true);
    // A failure is reported and the modal stays open; it is never written into
    // aiResult, which renders whatever it holds as if it were analysis.
    const fail = (message: string) =>
      addNotification({ type: 'error', title: 'Assessment Failed', message });
    try {
      let result: string | undefined;
      // For multiple entities (community/group), generate a community overview
      if (multiSelected.length > 1) {
        const entityNames = multiSelected.map(e => `${e.name} (${e.entity_type})`).join(', ');

        // Get stats for these entities if available
        const entityStats = stats?.entity_statistics?.filter(s =>
          multiSelected.some(e => e.name === s.entity)
        ) || [];
        const topByPagerank = [...entityStats].sort((a, b) => b.pagerank - a.pagerank).slice(0, 5);
        const topByBetweenness = [...entityStats].sort((a, b) => b.betweenness - a.betweenness).slice(0, 5);

        const statsContext = topByPagerank.length > 0
          ? `\n\nKey nodes by PageRank: ${topByPagerank.map(s => `${s.entity} (PR: ${s.pagerank.toFixed(4)})`).join(', ')}\nKey brokers by Betweenness: ${topByBetweenness.map(s => `${s.entity} (BC: ${s.betweenness.toFixed(4)})`).join(', ')}`
          : '';

        // Use RAG query for community context
        const ragRes = await queryApi.rag(activeProject.id,
          `Provide a comprehensive overview of the following group of entities and their relationships: ${entityNames}`
        );
        const ragContext = ragRes.data?.response || ragRes.data?.context || '';

        const communityPrompt = `Generate a community/group assessment for these ${multiSelected.length} entities:\n${entityNames}\n\n${statsContext}\n\nContext from knowledge graph:\n${ragContext}\n\nProvide:\n1. Community Overview (what binds this group together)\n2. Key Nodes (most influential members based on centrality)\n3. Internal Dynamics (relationship patterns within the group)\n4. External Connections (how this group connects to the broader network)\n5. Intelligence Gaps\n6. Assessment Summary`;

        const llmRes = await llmApi.query(
          [{ role: 'user', content: communityPrompt }],
          'threat_assessment'
        );
        // model "none" is the route's no-provider reply, whose content is a
        // configuration message rather than an assessment.
        if (llmRes.data?.model !== 'none') {
          result = llmRes.data?.response || llmRes.data?.content;
        }
      } else {
        // Single entity: use standard assessment
        const entity = multiSelected[0];
        const res = await assessApi.generate(entity.id, {
          entity_id: entity.id,
          project_id: activeProject.id,
          judgment: assessJudgment || undefined,
          probability: assessProbability,
        });
        // A failed generation is a 503 now; older backends sent 200 {error}.
        if (!res.data?.error) result = res.data?.assessment;
      }
      if (!result) {
        fail('No assessment was generated. Check the LLM configuration and try again.');
        return;
      }
      setAiResult(result);
      setAssessModalOpen(false);
      setAssessJudgment('');
      setAssessProbability(0.5);
      setAssessAnalyst('');
    } catch (e) {
      fail(getErrorMessage(e));
    } finally {
      setAssessLoading(false);
    }
  }

  async function gapAnalysis() {
    if (!selectedEntity || !activeProject) return;
    setAiLoading(true);
    try {
      // Grounded: the backend measures real coverage holes across the graph and
      // retrieves this entity's subgraph before reasoning — not a bare prompt.
      const res = await analysisApi.gaps({
        project_id: activeProject.id,
        entity_ids: [selectedEntity.id],
      });
      setAiResult(res.data.analysis);
    } catch (e) {
      // Never write the failure into aiResult — it renders as if it were analysis.
      addNotification({
        type: 'error',
        title: 'Gap Analysis Failed',
        message: getErrorMessage(e),
      });
    } finally {
      setAiLoading(false);
    }
  }

  async function competingHypotheses() {
    if (!selectedEntity || !activeProject) return;
    setAiLoading(true);
    try {
      // ACH over the entity's retrieved evidence, scored by the backend.
      const res = await analysisApi.hypotheses({
        project_id: activeProject.id,
        question: `What are the competing explanations for the role of ${selectedEntity.name} in this intelligence picture?`,
        entity_ids: [selectedEntity.id],
      });
      setAiResult(res.data.analysis);
    } catch (e) {
      addNotification({
        type: 'error',
        title: 'Hypothesis Generation Failed',
        message: getErrorMessage(e),
      });
    } finally {
      setAiLoading(false);
    }
  }

  return {
    aiLoading,
    assessModalOpen, setAssessModalOpen,
    assessJudgment, setAssessJudgment,
    assessProbability, setAssessProbability,
    assessAnalyst, setAssessAnalyst,
    assessLoading,
    submitAssessment,
    generateAssessment,
    generateAssessmentFromModal,
    gapAnalysis,
    competingHypotheses,
  };
}
