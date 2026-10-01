'use client';
import EnrichmentPanel from '@/components/EnrichmentPanel';
import { entityFields } from '@/lib/api';
import { TYPE_COLOR_CLASS as TYPE_COLORS } from '@/lib/entityStyles';
import { displayProperties } from '../graphFilters';
import { formatEntityType, type EgoNetworkData, type Entity, type GraphEdge } from '../types';
import type { useEntitySelection } from '../hooks/useEntitySelection';
import type { useNetworkAnalysis } from '../hooks/useNetworkAnalysis';
import RelationshipList from './RelationshipList';
import EvidenceDocuments from './EvidenceDocuments';
import EgoNetworkSection from './EgoNetworkSection';
import EntityActions from './EntityActions';
import { AiActions, AiResult } from './AiActions';

interface EntityPanelProps {
  entity: Entity;
  selection: ReturnType<typeof useEntitySelection>;
  analysis: ReturnType<typeof useNetworkAnalysis>;
  graphEdges: GraphEdge[];
  onFocusEgo: (ego: EgoNetworkData) => void;
  aiLoading: boolean;
  onGenerateAssessment: () => void;
  onGapAnalysis: () => void;
  onCompetingHypotheses: () => void;
  aiResult: string | null;
  typeDropdownOpen: boolean;
  setTypeDropdownOpen: (open: boolean) => void;
  onChangeType: (entityType: string) => void;
  onOpenDocument: (docId: string) => void;
}

/** The selected entity: properties, enrichment, relationships, evidence, ego network and actions. */
export default function EntityPanel({
  entity, selection, analysis, graphEdges, onFocusEgo,
  aiLoading, onGenerateAssessment, onGapAnalysis, onCompetingHypotheses, aiResult,
  typeDropdownOpen, setTypeDropdownOpen, onChangeType, onOpenDocument,
}: EntityPanelProps) {
  // Through entityFields: the entity routes flatten node fields onto the
  // object, so reading only `.properties` showed nothing for most entities.
  const propertyRows = displayProperties(entity);

  return (
    <div className="p-4 space-y-4">
      <div>
        <h3 className="font-bold text-lg">{entity.name}</h3>
        <span className={`inline-block mt-1 text-xs px-2 py-0.5 rounded ${TYPE_COLORS[entity.entity_type] || 'bg-gray-500'} text-white`}>
          {formatEntityType(entity.entity_type)}
        </span>
      </div>

      {propertyRows.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-gray-400 mb-2">Properties</h4>
          <div className="space-y-1">
            {propertyRows.map(([key, value]) => (
              <div key={key} className="text-xs break-words">
                <span className="text-gray-500">{key}:</span>{' '}
                <span className="text-gray-300">{value}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <EnrichmentPanel
        key={entity.id}
        entityId={entity.id}
        entityType={entity.entity_type}
        properties={entityFields(entity)}
        onEnriched={() => selection.refreshEnrichedEntity(entity.id)}
      />

      <RelationshipList
        selectedEntity={entity}
        entityRelationships={selection.entityRelationships}
        relationshipsError={selection.relationshipsError}
        onRetry={() => selection.selectEntity(entity)}
        graphEdges={graphEdges}
        relEvidenceOpen={selection.relEvidenceOpen}
        toggleRelEvidence={selection.toggleRelEvidence}
        evidenceDocs={selection.evidenceDocs}
        onOpenDocument={onOpenDocument}
      />

      {/* Evidence Chain: Source Documents */}
      <EvidenceDocuments
        loading={selection.evidenceLoading}
        error={selection.evidenceError}
        documents={selection.evidenceDocs}
        total={selection.evidenceTotal}
        onOpenDocument={onOpenDocument}
      />

      {/* Ego Network */}
      <EgoNetworkSection
        selectedEntity={entity}
        egoHops={analysis.egoHops}
        setEgoHops={analysis.setEgoHops}
        egoLoading={analysis.egoLoading}
        egoNetwork={analysis.egoNetwork}
        onExtract={analysis.loadEgoNetwork}
        selectEntity={selection.selectEntity}
        onFocus={onFocusEgo}
      />

      <AiActions
        aiLoading={aiLoading}
        onGenerateAssessment={onGenerateAssessment}
        onGapAnalysis={onGapAnalysis}
        onCompetingHypotheses={onCompetingHypotheses}
      />

      <EntityActions
        selectedEntity={entity}
        isWatchlisted={selection.isWatchlisted}
        watchlistLoading={selection.watchlistLoading}
        onToggleWatchlist={selection.toggleWatchlist}
        typeDropdownOpen={typeDropdownOpen}
        setTypeDropdownOpen={setTypeDropdownOpen}
        onChangeType={onChangeType}
      />

      <AiResult result={aiResult} />
    </div>
  );
}
