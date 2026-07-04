import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Network,
  Columns3,
  LogOut,
  Library,
  Boxes,
  ShieldCheck,
  Bot,
  GitCompareArrows,
  Radar,
  Target,
  Sparkles,
  ScanSearch,
  Table2,
  Hexagon,
  Search,
  Filter,
  History,
  ClipboardCheck,
  Users,
} from 'lucide-react';
import { api } from './api';
import { useStore, type View } from './store';
import { LoginView, useOidcCallback } from './components/LoginView';
import { startGapMap } from './lib/gapMapStream';
import { ChatView } from './components/ChatView';
import { AskView } from './components/AskView';
import { LibraryView } from './components/LibraryView';
import { CompareView } from './components/CompareView';
import { CoverageView } from './components/CoverageView';
import { GapsView } from './components/GapsView';
import { GlossaryView } from './components/GlossaryView';
import { AdvisorView } from './components/AdvisorView';
import { DashboardView } from './components/DashboardView';
import { GapMapView } from './components/GapMapView';
import { ContradictionsView } from './components/ContradictionsView';
import { EntityDetailView } from './components/EntityDetailView';
import { CurationView } from './components/CurationView';
import { AdminView } from './components/AdminView';
import { EvidenceDrawer } from './components/EvidenceDrawer';
// -- Batch-1 feature screens ------------------------------------------------
import { AgentReasoningTimelineView } from './components/AgentReasoningTimelineView';
import { ApplesToApplesView } from './components/ApplesToApplesView';
import { BenchmarkView } from './components/BenchmarkView';
import { CommunitySummariesView } from './components/CommunitySummariesView';
import { ERCandidatesView } from './components/ERCandidatesView';
import { EntityResolutionStepView } from './components/EntityResolutionStepView';
import { EvidencePackView } from './components/EvidencePackView';
import { FigureEvidenceView } from './components/FigureEvidenceView';
import { GapClosurePlanView } from './components/GapClosurePlanView';
import { GapMatrixView } from './components/GapMatrixView';
import { HardnessCompareView } from './components/HardnessCompareView';
import { HitlClarifyView } from './components/HitlClarifyView';
import { LargeGraphView } from './components/LargeGraphView';
import { LinkPredictionView } from './components/LinkPredictionView';
import { LiveGdsView } from './components/LiveGdsView';
import { SimilarLinksView } from './components/SimilarLinksView';
import { SourceTrustView } from './components/SourceTrustView';
import { ValueOfInformationView } from './components/ValueOfInformationView';
import { AbsenceMapView } from './components/AbsenceMapView';
import { MaterialCoverageHeatmapView } from './components/MaterialCoverageHeatmapView';
import { MissingLinksBoardView } from './components/MissingLinksBoardView';
// -- Batch-2 feature screens ------------------------------------------------
import { AgentTraceView } from './components/AgentTraceView';
import { RunTransparencyView } from './components/RunTransparencyView';
import { GraphPathSearchView } from './components/GraphPathSearchView';
import { EdgeAnomaliesView } from './components/EdgeAnomaliesView';
import { SchemaGraphExtractionView } from './components/SchemaGraphExtractionView';
import { SimilarEmbeddingsView } from './components/SimilarEmbeddingsView';
import { SimilarMaterialsView } from './components/SimilarMaterialsView';
import { SuspectValuesView } from './components/SuspectValuesView';
import { KgHealthView } from './components/KgHealthView';
import { CommunityClusterGraphView } from './components/CommunityClusterGraphView';
import { CoverageSankeyView } from './components/CoverageSankeyView';
import { GraphVisualEncodingView } from './components/GraphVisualEncodingView';
import { EvidenceBboxView } from './components/EvidenceBboxView';
import { ExtractionEvalView } from './components/ExtractionEvalView';
import { MlNerView } from './components/MlNerView';
import { MlflowExperimentsView } from './components/MlflowExperimentsView';
import { ProseClaimsView } from './components/ProseClaimsView';
import { QualityBoardView } from './components/QualityBoardView';
import { RagChecksView } from './components/RagChecksView';
import { TargetPictureDemoView } from './components/TargetPictureDemoView';
import { UnitProvenanceView } from './components/UnitProvenanceView';
// -- Batch-3 feature screens ------------------------------------------------
import { SearchHighlightView } from './components/SearchHighlightView';
import { GraphIntegrityView } from './components/GraphIntegrityView';
import { UnitReviewView } from './components/UnitReviewView';
import { ExtractorRunLineageView } from './components/ExtractorRunLineageView';
import { WarningPanelView } from './components/WarningPanelView';
import { ProvenanceCitationsView } from './components/ProvenanceCitationsView';
import { OpsDashboardsView } from './components/OpsDashboardsView';
import { SubgraphAskView } from './components/SubgraphAskView';
import { GraphQueryTemplatesView } from './components/GraphQueryTemplatesView';
import { FigureCaptionEvidenceView } from './components/FigureCaptionEvidenceView';
import { OcrBranchView } from './components/OcrBranchView';
import { BatchIngestView } from './components/BatchIngestView';
import { IngestPipelineView } from './components/IngestPipelineView';
import { ConfidenceFusionView } from './components/ConfidenceFusionView';
import { ErEvalView } from './components/ErEvalView';
import { RerankLiveView } from './components/RerankLiveView';
import { ExperimentExtractView } from './components/ExperimentExtractView';
import { MentionResolverView } from './components/MentionResolverView';
import { MergeUndoView } from './components/MergeUndoView';
import { EvidenceInspectorView } from './components/EvidenceInspectorView';
import { TableCorrectionView } from './components/TableCorrectionView';
// -- Batch-4 feature screens ------------------------------------------------
import { ArbiterEvidenceView } from './components/ArbiterEvidenceView';
import { ContradictionScanView } from './components/ContradictionScanView';
import { CoverageDashboardView } from './components/CoverageDashboardView';
import { CurationDiffReagraphView } from './components/CurationDiffReagraphView';
import DefinitionOfDoneView from './components/DefinitionOfDoneView';
import { ExtractionRecallEvalView } from './components/ExtractionRecallEvalView';
import { FacetSearchView } from './components/FacetSearchView';
import { CorpusExplorerView } from './components/CorpusExplorerView';
import { GraphExploreView } from './components/GraphExploreView';
import { EvidenceInspectorHubView } from './components/EvidenceInspectorHubView';
import { SourceTrustHubView } from './components/SourceTrustHubView';
import { CurationHubView } from './components/CurationHubView';
import { AgentReasoningHubView } from './components/AgentReasoningHubView';
import { FactTimeMachineView } from './components/FactTimeMachineView';
import { GoldenDatasetView } from './components/GoldenDatasetView';
import { GraphDiffView } from './components/GraphDiffView';
import { LangGraphStudioView } from './components/LangGraphStudioView';
import { LongTermMemoryView } from './components/LongTermMemoryView';
import { NewDocumentSensorView } from './components/NewDocumentSensorView';
import { PipelineLineageEmissionView } from './components/PipelineLineageEmissionView';
import { PipelineLineageView } from './components/PipelineLineageView';
import { RangeFacetsView } from './components/RangeFacetsView';
import { RankingExplainView } from './components/RankingExplainView';
import { RegressionGateView } from './components/RegressionGateView';
import { RetrievalEvalDashboardView } from './components/RetrievalEvalDashboardView';
import { ReviewTaskGenView } from './components/ReviewTaskGenView';
import { SourceCatalogView } from './components/SourceCatalogView';
import { SubgraphChatAttachView } from './components/SubgraphChatAttachView';
import { VerifierGateView } from './components/VerifierGateView';
// -- Batch-5 feature screens ------------------------------------------------
import { CollaborationView } from './components/CollaborationView';
import { ConfidenceCalibrationView } from './components/ConfidenceCalibrationView';
import { DagsterAssetGraphView } from './components/DagsterAssetGraphView';
import { ERMetricsView } from './components/ERMetricsView';
import { EntityTimelineView } from './components/EntityTimelineView';
import { ExpertFeedbackView } from './components/ExpertFeedbackView';
import { GraphLegendView } from './components/GraphLegendView';
import { LocaleSwitcherView } from './components/LocaleSwitcherView';
import { MaterialsNerView } from './components/MaterialsNerView';
import { PipelineAgentDagView } from './components/PipelineAgentDagView';
import { PropertyTermReviewView } from './components/PropertyTermReviewView';

const INTERNAL = ['researcher', 'analyst', 'curator', 'project_manager', 'admin'];
const CURATOR = ['curator', 'project_manager', 'admin'];

// Grouped navigation — with ~70 screens a flat icon rail is unusable, so the sidebar
// groups them into labelled, collapsible sections with a filter. Order = display order.
type Grp =
  | 'overview'
  | 'qa'
  | 'gaps'
  | 'knowledge'
  | 'graph'
  | 'evidence'
  | 'data'
  | 'quality'
  | 'curation'
  | 'agent'
  | 'admin';

// Jury-facing sidebar: 86→25 screens across 9 product groups. Engineering groups
// «Данные и извлечение» / «Качество и оценка» are fully hidden (their screens' routes
// stay in code). data/quality remain valid Grp members but have no visible group here.
const GROUPS: { id: Grp; label: string }[] = [
  { id: 'overview', label: 'Обзор' },
  { id: 'qa', label: 'Вопросы и ответы' },
  { id: 'gaps', label: 'Пробелы и противоречия' },
  { id: 'knowledge', label: 'Аналитика знаний' },
  { id: 'graph', label: 'Граф и связи' },
  { id: 'evidence', label: 'Доказательства и доверие' },
  { id: 'curation', label: 'Курирование' },
  { id: 'agent', label: 'Ассистент и демо' },
  { id: 'admin', label: 'Администрирование' },
];

type NavItem = { id: View; label: string; icon: typeof Network; roles?: string[]; group: Grp };

const NAV: NavItem[] = [
  { id: 'dashboard', label: 'Обзор базы знаний', icon: Radar, group: 'overview' },

  { id: 'ask', label: 'Запрос к графу', icon: Network, group: 'qa' },
  { id: 'advisor', label: 'Советник', icon: Bot, group: 'qa' },
  { id: 'compare', label: 'Сравнение технологий', icon: Columns3, group: 'qa' },
  { id: 'library', label: 'Библиотека', icon: Library, roles: INTERNAL, group: 'qa' },

  { id: 'gapmap', label: 'Карта пробелов', icon: Target, roles: INTERNAL, group: 'gaps' },
  { id: 'contradictions', label: 'Противоречия', icon: GitCompareArrows, roles: INTERNAL, group: 'gaps' },

  { id: 'corpusexplore', label: 'Поиск по корпусу', icon: Filter, group: 'knowledge' },
  { id: 'coverageMatrix', label: 'Матрица покрытия', icon: Table2, roles: INTERNAL, group: 'knowledge' },
  { id: 'clustergraph', label: 'Карта кластеров', icon: Hexagon, group: 'knowledge' },
  { id: 'facttimemachine', label: 'Машина времени фактов', icon: History, roles: INTERNAL, group: 'knowledge' },

  { id: 'graph-explore', label: 'Сущности и похожие', icon: Boxes, group: 'graph' },

  { id: 'evidence-inspector', label: 'Инспектор доказательств', icon: ScanSearch, roles: INTERNAL, group: 'evidence' },
  { id: 'source-trust', label: 'Доверие к источникам', icon: ShieldCheck, roles: INTERNAL, group: 'evidence' },

  { id: 'curation-hub', label: 'Курирование', icon: ClipboardCheck, roles: CURATOR, group: 'curation' },

  { id: 'targetdemo', label: 'Демонстрационный прогон', icon: Sparkles, group: 'agent' },
  { id: 'collaboration', label: 'Совместная работа', icon: Users, roles: CURATOR, group: 'agent' },

  { id: 'admin', label: 'Администрирование', icon: ShieldCheck, roles: CURATOR, group: 'admin' },
];

export function App() {
  const { view, setView, role, useLlm, setUseLlm, user, signOut } = useStore();
  useOidcCallback();
  const stats = useQuery({ queryKey: ['stats'], queryFn: api.stats, enabled: !!user });
  const [filter, setFilter] = useState('');
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  // Прогреваем «Карту пробелов» сразу после входа: приоритизация стримится в фоне и
  // кэшируется в сторе, поэтому к моменту открытия экрана карточки уже готовы (no-op при повторе).
  useEffect(() => {
    if (user) startGapMap();
  }, [user]);

  const nav = useMemo(() => NAV.filter((n) => !n.roles || n.roles.includes(role)), [role]);
  const q = filter.trim().toLowerCase();
  const visible = q ? nav.filter((n) => n.label.toLowerCase().includes(q)) : nav;

  // Gate the whole app on sign-in — «красивая авторизация» first.
  if (!user) return <LoginView />;
  if (!nav.some((n) => n.id === view)) setView('dashboard');

  const toggle = (g: string) =>
    setCollapsed((s) => {
      const n = new Set(s);
      if (n.has(g)) n.delete(g);
      else n.add(g);
      return n;
    });

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Left sidebar — grouped, labelled, filterable */}
      <aside className="flex w-60 shrink-0 flex-col border-r border-line bg-graphite/60">
        <div className="flex items-center gap-2.5 border-b border-line px-4 py-3.5">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-copper/15 text-copper">
            <ClubokMark />
          </div>
          <div className="min-w-0">
            <div className="truncate font-display text-sm font-semibold tracking-tight text-ink">
              Научный клубок
            </div>
            <div className="truncate font-mono text-[9px] uppercase tracking-wide text-faint">
              R&D knowledge graph
            </div>
          </div>
        </div>

        {/* Filter */}
        <div className="border-b border-line p-2">
          <div className="flex items-center gap-2 rounded-md border border-line bg-surface/60 px-2.5 py-1.5">
            <Search size={13} className="shrink-0 text-faint" />
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Поиск раздела…"
              className="min-w-0 flex-1 bg-transparent text-xs text-ink outline-none placeholder:text-faint"
            />
            {filter && (
              <button onClick={() => setFilter('')} className="text-faint hover:text-nickel">
                <ChevronRight size={12} className="rotate-45" />
              </button>
            )}
          </div>
        </div>

        <nav className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
          {GROUPS.map((grp) => {
            const items = visible.filter((n) => n.group === grp.id);
            if (items.length === 0) return null;
            const isCollapsed = !q && collapsed.has(grp.id);
            return (
              <div key={grp.id} className="mb-1">
                {!q && (
                  <button
                    onClick={() => toggle(grp.id)}
                    className="flex w-full items-center gap-1 px-2 py-1 font-mono text-[9px] uppercase tracking-wider text-faint transition hover:text-nickel"
                  >
                    {isCollapsed ? <ChevronRight size={10} /> : <ChevronDown size={10} />}
                    {grp.label}
                    <span className="ml-auto text-faint/60">{items.length}</span>
                  </button>
                )}
                {!isCollapsed &&
                  items.map(({ id, label, icon: Icon }) => (
                    <button
                      key={id}
                      onClick={() => setView(id)}
                      className={`group flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left text-[13px] transition-colors ${
                        view === id
                          ? 'bg-copper/15 text-copper'
                          : 'text-muted hover:bg-surface/60 hover:text-nickel'
                      }`}
                    >
                      <Icon size={15} strokeWidth={1.75} className="shrink-0" />
                      <span className="truncate">{label}</span>
                    </button>
                  ))}
              </div>
            );
          })}
          {visible.length === 0 && (
            <div className="px-2 py-6 text-center font-mono text-[11px] text-faint">
              ничего не найдено
            </div>
          )}
        </nav>
        <div className="flex items-center gap-1.5 border-t border-line px-3 py-2 font-mono text-[9px] text-faint">
          <CircleHelp size={11} /> только OSS-модели · {nav.length} разделов
        </div>
      </aside>

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-line px-6 py-3">
          <div>
            <div className="eyebrow">Горно-металлургический R&D · knowledge graph</div>
            <h1 className="font-display text-xl font-semibold tracking-tight">
              Научный клубок
            </h1>
          </div>
          <div className="flex items-center gap-4 text-xs">
            {stats.data && (
              <span className="chip text-muted">
                <span className="h-1.5 w-1.5 rounded-full bg-verified" />
                {stats.data.counts.nodes.toLocaleString('ru')} узлов ·{' '}
                {stats.data.counts.rels.toLocaleString('ru')} связей
              </span>
            )}
            <label className="flex cursor-pointer items-center gap-2 text-muted">
              <input
                type="checkbox"
                checked={useLlm}
                onChange={(e) => setUseLlm(e.target.checked)}
                className="accent-copper"
              />
              <span className="eyebrow">LLM-синтез</span>
            </label>
            {/* Signed-in identity + role + sign-out */}
            <div className="flex items-center gap-2 rounded-md border border-line bg-surface/60 px-2.5 py-1">
              <span className="h-1.5 w-1.5 rounded-full bg-verified" />
              <span className="text-ink">{user}</span>
              <span className="font-mono text-[10px] uppercase tracking-wide text-copper">{role}</span>
              <button
                onClick={signOut}
                title="Выйти"
                className="ml-1 text-faint transition hover:text-contradiction"
              >
                <LogOut size={14} />
              </button>
            </div>
          </div>
        </header>

        <main className="min-h-0 flex-1 overflow-hidden">
          {view === 'dashboard' && <DashboardView />}
          {view === 'chat' && <ChatView />}
          {view === 'advisor' && <AdvisorView />}
          {view === 'ask' && <AskView />}
          {view === 'library' && <LibraryView />}
          {view === 'compare' && <CompareView />}
          {view === 'coverage' && <CoverageView />}
          {view === 'gaps' && <GapsView />}
          {view === 'gapmap' && <GapMapView />}
          {view === 'contradictions' && <ContradictionsView />}
          {view === 'entities' && <EntityDetailView />}
          {view === 'glossary' && <GlossaryView />}
          {view === 'corpusexplore' && <CorpusExplorerView />}
          {view === 'graph-explore' && <GraphExploreView />}
          {view === 'evidence-inspector' && <EvidenceInspectorHubView />}
          {view === 'source-trust' && <SourceTrustHubView />}
          {view === 'curation-hub' && <CurationHubView />}
          {view === 'agent-reasoning' && <AgentReasoningHubView />}
          {view === 'curation' && <CurationView />}
          {view === 'admin' && <AdminView />}
          {/* -- Batch-1 feature screens -- */}
          {view === 'reasoning' && <AgentReasoningTimelineView />}
          {view === 'hitl' && <HitlClarifyView />}
          {view === 'communities' && <CommunitySummariesView />}
          {view === 'largegraph' && <LargeGraphView />}
          {view === 'livegds' && <LiveGdsView />}
          {view === 'apples' && <ApplesToApplesView />}
          {view === 'hardness' && <HardnessCompareView />}
          {view === 'coverageMatrix' && <MaterialCoverageHeatmapView />}
          {view === 'gapmatrix' && <GapMatrixView />}
          {view === 'gapplan' && <GapClosurePlanView />}
          {view === 'linkpred' && <LinkPredictionView />}
          {view === 'simlinks' && <SimilarLinksView />}
          {view === 'missinglinks' && <MissingLinksBoardView />}
          {view === 'absence' && <AbsenceMapView />}
          {view === 'voi' && <ValueOfInformationView />}
          {view === 'figures' && <FigureEvidenceView />}
          {view === 'evidencepack' && <EvidencePackView />}
          {view === 'sourcetrust' && <SourceTrustView />}
          {view === 'benchmark' && <BenchmarkView />}
          {view === 'er_candidates' && <ERCandidatesView />}
          {view === 'erstep' && <EntityResolutionStepView />}
          {/* -- Batch-2 feature screens -- */}
          {view === 'targetdemo' && <TargetPictureDemoView />}
          {view === 'clustergraph' && <CommunityClusterGraphView />}
          {view === 'coveragesankey' && <CoverageSankeyView />}
          {view === 'graphencoding' && <GraphVisualEncodingView />}
          {view === 'simembed' && <SimilarEmbeddingsView />}
          {view === 'similarMaterials' && <SimilarMaterialsView />}
          {view === 'graphpath' && <GraphPathSearchView />}
          {view === 'unitprov' && <UnitProvenanceView />}
          {view === 'mlner' && <MlNerView />}
          {view === 'mlflow' && <MlflowExperimentsView />}
          {view === 'schemaextract' && <SchemaGraphExtractionView />}
          {view === 'evidencebbox' && <EvidenceBboxView />}
          {view === 'edgeanomalies' && <EdgeAnomaliesView />}
          {view === 'agenttrace' && <AgentTraceView />}
          {view === 'runtransparency' && <RunTransparencyView />}
          {view === 'proseclaims' && <ProseClaimsView />}
          {view === 'extraction_eval' && <ExtractionEvalView />}
          {view === 'qualityboard' && <QualityBoardView />}
          {view === 'ragchecks' && <RagChecksView />}
          {view === 'suspects' && <SuspectValuesView />}
          {view === 'kghealth' && <KgHealthView />}
          {/* -- Batch-3 feature screens -- */}
          {view === 'searchhl' && <SearchHighlightView />}
          {view === 'subgraphask' && <SubgraphAskView />}
          {view === 'graphtemplates' && <GraphQueryTemplatesView />}
          {view === 'figcaptions' && <FigureCaptionEvidenceView />}
          {view === 'evidenceinspector' && <EvidenceInspectorView />}
          {view === 'provcitations' && <ProvenanceCitationsView />}
          {view === 'warnings' && <WarningPanelView />}
          {view === 'confidencefusion' && <ConfidenceFusionView />}
          {view === 'extractorrun' && <ExtractorRunLineageView />}
          {view === 'experimentextract' && <ExperimentExtractView />}
          {view === 'reranklive' && <RerankLiveView />}
          {view === 'ereval' && <ErEvalView />}
          {view === 'opsdash' && <OpsDashboardsView />}
          {view === 'ocr' && <OcrBranchView />}
          {view === 'batchingest' && <BatchIngestView />}
          {view === 'ingestpipeline' && <IngestPipelineView />}
          {view === 'mentionresolve' && <MentionResolverView />}
          {view === 'mergeundo' && <MergeUndoView />}
          {view === 'tablecorrection' && <TableCorrectionView />}
          {view === 'unitreview' && <UnitReviewView />}
          {view === 'graphintegrity' && <GraphIntegrityView />}
          {/* -- Batch-4 feature screens -- */}
          {view === 'arbiterEvidence' && <ArbiterEvidenceView />}
          {view === 'contradictionScan' && <ContradictionScanView />}
          {view === 'coveragedash' && <CoverageDashboardView />}
          {view === 'curationdiffreagraph' && <CurationDiffReagraphView />}
          {view === 'dod' && <DefinitionOfDoneView />}
          {view === 'extractionrecall' && <ExtractionRecallEvalView />}
          {view === 'facetsearch' && <FacetSearchView />}
          {view === 'facttimemachine' && <FactTimeMachineView />}
          {view === 'goldendataset' && <GoldenDatasetView />}
          {view === 'graphdiff' && <GraphDiffView />}
          {view === 'langgraphstudio' && <LangGraphStudioView />}
          {view === 'ltmemory' && <LongTermMemoryView />}
          {view === 'newdocsensor' && <NewDocumentSensorView />}
          {view === 'pipelineemission' && <PipelineLineageEmissionView />}
          {view === 'pipelinelineage' && <PipelineLineageView />}
          {view === 'rangefacets' && <RangeFacetsView />}
          {view === 'rankingexplain' && <RankingExplainView />}
          {view === 'regressiongate' && <RegressionGateView />}
          {view === 'retrievaleval' && <RetrievalEvalDashboardView />}
          {view === 'reviewtaskgen' && <ReviewTaskGenView />}
          {view === 'sourcecatalog' && <SourceCatalogView />}
          {view === 'subgraphchat' && <SubgraphChatAttachView />}
          {view === 'verifiergate' && <VerifierGateView />}
          {/* -- Batch-5 feature screens -- */}
          {view === 'graphlegend' && <GraphLegendView />}
          {view === 'entitytimeline' && <EntityTimelineView />}
          {view === 'materialsner' && <MaterialsNerView />}
          {view === 'dagsterassets' && <DagsterAssetGraphView />}
          {view === 'calibration' && <ConfidenceCalibrationView />}
          {view === 'expertfeedback' && <ExpertFeedbackView />}
          {view === 'propertytermreview' && <PropertyTermReviewView />}
          {view === 'collaboration' && <CollaborationView />}
          {view === 'pipelineagentdag' && <PipelineAgentDagView />}
          {view === 'ermetrics' && <ERMetricsView />}
          {view === 'localeswitcher' && <LocaleSwitcherView />}
        </main>
      </div>

      <EvidenceDrawer />
    </div>
  );
}

function ClubokMark() {
  // A small tangle: three intertwined threads → the "клубок".
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
      <circle cx="10" cy="10" r="7" stroke="currentColor" strokeWidth="1.1" opacity="0.5" />
      <path d="M4 10c3-4 9-4 12 0M4 10c3 4 9 4 12 0M10 3v14" stroke="currentColor" strokeWidth="1.1" />
    </svg>
  );
}
