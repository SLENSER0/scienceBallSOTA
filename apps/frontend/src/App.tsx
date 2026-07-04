import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  ChevronDown,
  ChevronRight,
  CircleHelp,
  LayoutGrid,
  Network,
  BookMarked,
  TriangleAlert,
  Columns3,
  MessagesSquare,
  LogOut,
  Library,
  Boxes,
  ClipboardList,
  ShieldCheck,
  Bot,
  GitCompareArrows,
  Radar,
  Target,
  Route,
  Scale,
  Trophy,
  Sparkles,
  Layers,
  Workflow,
  PackageCheck,
  Image as ImageIcon,
  FlaskConical,
  Grid3x3,
  Gauge,
  Waypoints,
  GitFork,
  Wand2,
  Share2,
  Lightbulb,
  Compass,
  Table2,
  Spline,
  Hexagon,
  MapPin,
  ScanText,
  ScrollText,
  Activity,
  FileCode2,
  Shapes,
  Fingerprint,
  GitBranch,
  Palette,
  HeartPulse,
  Highlighter,
  Quote,
  Lasso,
  Undo2,
  Ruler,
  FileStack,
  Search,
  Code2,
  Wrench,
  ShieldAlert,
} from 'lucide-react';
import { api } from './api';
import { useStore, type View } from './store';
import { LoginView, useOidcCallback } from './components/LoginView';
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

const INTERNAL = ['researcher', 'analyst', 'curator', 'project_manager', 'admin'];
const CURATOR = ['curator', 'project_manager', 'admin'];
const ANALYST = ['analyst', 'curator', 'project_manager', 'admin'];

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

const GROUPS: { id: Grp; label: string }[] = [
  { id: 'overview', label: 'Обзор' },
  { id: 'qa', label: 'Вопросы и ответы' },
  { id: 'gaps', label: 'Пробелы · противоречия' },
  { id: 'knowledge', label: 'Аналитика знаний' },
  { id: 'graph', label: 'Граф и связи' },
  { id: 'evidence', label: 'Доказательства · доверие' },
  { id: 'data', label: 'Данные и извлечение' },
  { id: 'quality', label: 'Качество и оценка' },
  { id: 'curation', label: 'Курирование' },
  { id: 'agent', label: 'Агент · внутренности' },
  { id: 'admin', label: 'Администрирование' },
];

type NavItem = { id: View; label: string; icon: typeof Network; roles?: string[]; group: Grp };

const NAV: NavItem[] = [
  { id: 'dashboard', label: 'Обзор базы знаний', icon: Radar, group: 'overview' },

  { id: 'chat', label: 'Диалог с клубком', icon: MessagesSquare, group: 'qa' },
  { id: 'advisor', label: 'Советник (рекомендации)', icon: Bot, group: 'qa' },
  { id: 'ask', label: 'Запрос к графу', icon: Network, group: 'qa' },
  { id: 'compare', label: 'Сравнение технологий', icon: Columns3, group: 'qa' },
  { id: 'library', label: 'Библиотека · deep-research', icon: Library, roles: INTERNAL, group: 'qa' },

  { id: 'gaps', label: 'Пробелы и риски', icon: TriangleAlert, roles: INTERNAL, group: 'gaps' },
  { id: 'gapmap', label: 'Карта пробелов', icon: Target, roles: INTERNAL, group: 'gaps' },
  { id: 'gapmatrix', label: 'Матрица пробелов', icon: Grid3x3, roles: INTERNAL, group: 'gaps' },
  { id: 'gapplan', label: 'План экспериментов', icon: FlaskConical, roles: INTERNAL, group: 'gaps' },
  { id: 'absence', label: 'Карта неизвестного', icon: Compass, roles: INTERNAL, group: 'gaps' },
  { id: 'voi', label: 'Ценность информации', icon: Lightbulb, roles: INTERNAL, group: 'gaps' },
  { id: 'contradictions', label: 'Противоречия (арбитр)', icon: GitCompareArrows, roles: INTERNAL, group: 'gaps' },

  { id: 'coverage', label: 'Покрытие по доменам', icon: LayoutGrid, group: 'knowledge' },
  { id: 'coverageMatrix', label: 'Матрица покрытия', icon: Table2, roles: INTERNAL, group: 'knowledge' },
  { id: 'coveragesankey', label: 'Потоки покрытия', icon: Workflow, group: 'knowledge' },
  { id: 'communities', label: 'Сообщества (GraphRAG)', icon: Sparkles, group: 'knowledge' },
  { id: 'clustergraph', label: 'Карта кластеров', icon: Hexagon, group: 'knowledge' },
  { id: 'kghealth', label: 'Здоровье графа', icon: HeartPulse, roles: CURATOR, group: 'knowledge' },
  { id: 'graphintegrity', label: 'Целостность графа', icon: ShieldAlert, roles: CURATOR, group: 'knowledge' },
  { id: 'graphencoding', label: 'Легенда достоверности', icon: Palette, group: 'knowledge' },
  { id: 'glossary', label: 'Глоссарий', icon: BookMarked, group: 'knowledge' },

  { id: 'entities', label: 'Сущности (детали)', icon: Boxes, group: 'graph' },
  { id: 'largegraph', label: 'Клубок корпуса (WebGL)', icon: Waypoints, group: 'graph' },
  { id: 'livegds', label: 'Живой GDS', icon: Wand2, roles: INTERNAL, group: 'graph' },
  { id: 'graphpath', label: 'Путь между сущностями', icon: Route, roles: INTERNAL, group: 'graph' },
  { id: 'graphtemplates', label: 'Шаблоны запросов', icon: Code2, roles: INTERNAL, group: 'graph' },
  { id: 'subgraphask', label: 'Спросить о подграфе', icon: Lasso, roles: INTERNAL, group: 'graph' },
  { id: 'linkpred', label: 'Предсказание связей', icon: GitFork, roles: INTERNAL, group: 'graph' },
  { id: 'simlinks', label: 'Вероятные связи', icon: Share2, roles: INTERNAL, group: 'graph' },
  { id: 'missinglinks', label: 'Неявные связи', icon: Spline, roles: INTERNAL, group: 'graph' },
  { id: 'similarMaterials', label: 'Похожие материалы', icon: Layers, roles: INTERNAL, group: 'graph' },
  { id: 'simembed', label: 'Похожие (эмбеддинги)', icon: Hexagon, group: 'graph' },

  { id: 'evidenceinspector', label: 'Инспектор evidence', icon: Search, roles: INTERNAL, group: 'evidence' },
  { id: 'evidencebbox', label: 'Bbox-цитаты', icon: MapPin, roles: INTERNAL, group: 'evidence' },
  { id: 'figures', label: 'Фигуры-доказательства', icon: ImageIcon, roles: INTERNAL, group: 'evidence' },
  { id: 'figcaptions', label: 'Подписи как evidence', icon: Quote, roles: INTERNAL, group: 'evidence' },
  { id: 'provcitations', label: 'Провенанс цитат', icon: Fingerprint, roles: INTERNAL, group: 'evidence' },
  { id: 'sourcetrust', label: 'Доверие к источникам', icon: ShieldCheck, roles: INTERNAL, group: 'evidence' },
  { id: 'warnings', label: 'Панель предупреждений', icon: ShieldAlert, roles: INTERNAL, group: 'evidence' },
  { id: 'evidencepack', label: 'Evidence Pack (экспорт)', icon: PackageCheck, roles: INTERNAL, group: 'evidence' },
  { id: 'searchhl', label: 'Подсветка в поиске', icon: Highlighter, group: 'evidence' },

  { id: 'batchingest', label: 'Пакетный приём', icon: FileStack, roles: INTERNAL, group: 'data' },
  { id: 'ingestpipeline', label: 'Конвейер приёма', icon: Workflow, roles: INTERNAL, group: 'data' },
  { id: 'ocr', label: 'OCR сканов', icon: ScanText, roles: INTERNAL, group: 'data' },
  { id: 'proseclaims', label: 'Факты из прозы', icon: ScrollText, roles: ANALYST, group: 'data' },
  { id: 'schemaextract', label: 'Схема-экстракция', icon: Shapes, roles: INTERNAL, group: 'data' },
  { id: 'experimentextract', label: 'ExperimentExtract', icon: FlaskConical, roles: ANALYST, group: 'data' },
  { id: 'extractorrun', label: 'Прогоны экстрактора', icon: GitBranch, roles: INTERNAL, group: 'data' },
  { id: 'mlner', label: 'ML-NER (GLiNER)', icon: ScanText, roles: INTERNAL, group: 'data' },

  { id: 'benchmark', label: 'Бенчмарк (SOTA)', icon: Trophy, roles: ANALYST, group: 'quality' },
  { id: 'ragchecks', label: 'RAGAS / DeepEval', icon: ShieldCheck, roles: ANALYST, group: 'quality' },
  { id: 'extraction_eval', label: 'Extraction eval', icon: Gauge, roles: ANALYST, group: 'quality' },
  { id: 'qualityboard', label: 'Табло качества', icon: Activity, roles: ANALYST, group: 'quality' },
  { id: 'mlflow', label: 'MLflow эксперименты', icon: FlaskConical, roles: INTERNAL, group: 'quality' },
  { id: 'ereval', label: 'Качество ER (F1)', icon: Gauge, roles: ANALYST, group: 'quality' },
  { id: 'opsdash', label: 'Ops-дашборды', icon: Activity, roles: ANALYST, group: 'quality' },
  { id: 'reranklive', label: 'Reranker (live)', icon: Layers, roles: ANALYST, group: 'quality' },
  { id: 'suspects', label: 'Подозрительные значения', icon: TriangleAlert, roles: CURATOR, group: 'quality' },
  { id: 'unitprov', label: 'Провенанс единиц', icon: Fingerprint, roles: INTERNAL, group: 'quality' },
  { id: 'unitreview', label: 'Единицы на ревью', icon: Ruler, roles: CURATOR, group: 'quality' },
  { id: 'apples', label: 'Единые единицы', icon: Scale, group: 'quality' },
  { id: 'hardness', label: 'Твёрдость HV↔HRC↔HB', icon: Gauge, group: 'quality' },

  { id: 'curation', label: 'Очередь курирования', icon: ClipboardList, roles: CURATOR, group: 'curation' },
  { id: 'er_candidates', label: 'Слияние сущностей', icon: Layers, roles: CURATOR, group: 'curation' },
  { id: 'erstep', label: 'ER-шаг конвейера', icon: Workflow, roles: INTERNAL, group: 'curation' },
  { id: 'mentionresolve', label: 'Резолвер упоминаний', icon: Target, roles: CURATOR, group: 'curation' },
  { id: 'mergeundo', label: 'Откат слияний', icon: Undo2, roles: CURATOR, group: 'curation' },
  { id: 'tablecorrection', label: 'Правка таблиц', icon: Wrench, roles: CURATOR, group: 'curation' },

  { id: 'reasoning', label: 'Ход мысли', icon: Route, group: 'agent' },
  { id: 'agenttrace', label: 'Трейс агента', icon: GitBranch, roles: INTERNAL, group: 'agent' },
  { id: 'runtransparency', label: 'Прозрачность прогона', icon: FileCode2, roles: INTERNAL, group: 'agent' },
  { id: 'hitl', label: 'Уточнение (HITL)', icon: CircleHelp, group: 'agent' },
  { id: 'confidencefusion', label: 'Слияние уверенности', icon: Layers, roles: INTERNAL, group: 'agent' },
  { id: 'edgeanomalies', label: 'Аномалии рёбер', icon: GitFork, roles: INTERNAL, group: 'agent' },
  { id: 'targetdemo', label: 'Демо-прогон §23', icon: Sparkles, group: 'agent' },

  { id: 'admin', label: 'Администрирование', icon: ShieldCheck, roles: CURATOR, group: 'admin' },
];

export function App() {
  const { view, setView, role, useLlm, setUseLlm, user, signOut } = useStore();
  useOidcCallback();
  const stats = useQuery({ queryKey: ['stats'], queryFn: api.stats, enabled: !!user });
  const [filter, setFilter] = useState('');
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

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
