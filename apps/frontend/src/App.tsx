import { useQuery } from '@tanstack/react-query';
import {
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

const INTERNAL = ['researcher', 'analyst', 'curator', 'project_manager', 'admin'];
const CURATOR = ['curator', 'project_manager', 'admin'];

const NAV: { id: View; label: string; icon: typeof Network; roles?: string[] }[] = [
  { id: 'dashboard', label: 'Обзор', icon: Radar },
  { id: 'chat', label: 'Диалог', icon: MessagesSquare },
  { id: 'advisor', label: 'Советник', icon: Bot },
  { id: 'ask', label: 'Запрос', icon: Network },
  // Adding articles is a curator/researcher capability, not for external partners.
  { id: 'library', label: 'Библиотека', icon: Library, roles: ['researcher', 'analyst', 'curator', 'project_manager', 'admin'] },
  { id: 'compare', label: 'Сравнение', icon: Columns3 },
  { id: 'coverage', label: 'Покрытие', icon: LayoutGrid },
  // External partners get a restricted view — no internal gap/risk analytics.
  { id: 'gaps', label: 'Пробелы и риски', icon: TriangleAlert, roles: ['researcher', 'analyst', 'curator', 'project_manager', 'admin'] },
  { id: 'gapmap', label: 'Карта пробелов', icon: Target, roles: ['researcher', 'analyst', 'curator', 'project_manager', 'admin'] },
  { id: 'contradictions', label: 'Противоречия', icon: GitCompareArrows, roles: ['researcher', 'analyst', 'curator', 'project_manager', 'admin'] },
  { id: 'entities', label: 'Сущности', icon: Boxes },
  { id: 'glossary', label: 'Глоссарий', icon: BookMarked },
  // Curation + governance are internal-team surfaces.
  { id: 'curation', label: 'Курирование', icon: ClipboardList, roles: ['curator', 'project_manager', 'admin'] },
  { id: 'admin', label: 'Администрирование', icon: ShieldCheck, roles: ['curator', 'project_manager', 'admin'] },

  // -- Batch-1 feature screens ----------------------------------------------
  { id: 'reasoning', label: 'Ход мысли', icon: Route },
  { id: 'hitl', label: 'Уточнение (HITL)', icon: CircleHelp },
  { id: 'communities', label: 'Сообщества', icon: Sparkles },
  { id: 'largegraph', label: 'Клубок корпуса', icon: Waypoints },
  { id: 'livegds', label: 'Живой GDS', icon: Wand2, roles: INTERNAL },
  { id: 'apples', label: 'Единые единицы', icon: Scale },
  { id: 'hardness', label: 'Твёрдость HV↔HRC↔HB', icon: Gauge },
  { id: 'coverageMatrix', label: 'Матрица покрытия', icon: Table2, roles: INTERNAL },
  { id: 'gapmatrix', label: 'Матрица пробелов', icon: Grid3x3, roles: INTERNAL },
  { id: 'gapplan', label: 'План экспериментов', icon: FlaskConical, roles: INTERNAL },
  { id: 'linkpred', label: 'Предсказание связей', icon: GitFork, roles: INTERNAL },
  { id: 'simlinks', label: 'Вероятные связи', icon: Share2, roles: INTERNAL },
  { id: 'missinglinks', label: 'Неявные связи', icon: Spline, roles: INTERNAL },
  { id: 'absence', label: 'Карта неизвестного', icon: Compass, roles: INTERNAL },
  { id: 'voi', label: 'Ценность информации', icon: Lightbulb, roles: INTERNAL },
  { id: 'figures', label: 'Фигуры-доказательства', icon: ImageIcon, roles: INTERNAL },
  { id: 'evidencepack', label: 'Evidence Pack', icon: PackageCheck, roles: INTERNAL },
  { id: 'sourcetrust', label: 'Доверие к источникам', icon: ShieldCheck, roles: INTERNAL },
  { id: 'benchmark', label: 'Бенчмарк', icon: Trophy, roles: ['analyst', 'curator', 'project_manager', 'admin'] },
  { id: 'er_candidates', label: 'Слияние сущностей', icon: Layers, roles: CURATOR },
  { id: 'erstep', label: 'ER-шаг конвейера', icon: Workflow, roles: INTERNAL },

  // -- Batch-2 feature screens ----------------------------------------------
  { id: 'targetdemo', label: 'Демо-прогон §23', icon: Sparkles },
  { id: 'clustergraph', label: 'Карта кластеров', icon: Hexagon },
  { id: 'coveragesankey', label: 'Потоки покрытия', icon: Workflow },
  { id: 'graphencoding', label: 'Легенда достоверности', icon: Palette },
  { id: 'simembed', label: 'Похожие (эмбеддинги)', icon: Boxes },
  { id: 'similarMaterials', label: 'Похожие материалы', icon: Boxes, roles: INTERNAL },
  { id: 'graphpath', label: 'Путь между сущностями', icon: Waypoints, roles: INTERNAL },
  { id: 'unitprov', label: 'Провенанс единиц', icon: Fingerprint, roles: INTERNAL },
  { id: 'mlner', label: 'ML-NER (GLiNER)', icon: ScanText, roles: INTERNAL },
  { id: 'mlflow', label: 'MLflow эксперименты', icon: FlaskConical, roles: INTERNAL },
  { id: 'schemaextract', label: 'Схема-экстракция', icon: Shapes, roles: INTERNAL },
  { id: 'evidencebbox', label: 'Bbox-цитаты', icon: MapPin, roles: INTERNAL },
  { id: 'edgeanomalies', label: 'Аномалии рёбер', icon: GitFork, roles: INTERNAL },
  { id: 'agenttrace', label: 'Трейс агента', icon: GitBranch, roles: INTERNAL },
  { id: 'runtransparency', label: 'Прозрачность прогона', icon: FileCode2, roles: INTERNAL },
  { id: 'proseclaims', label: 'Факты из прозы', icon: ScrollText, roles: ['analyst', 'curator', 'project_manager', 'admin'] },
  { id: 'extraction_eval', label: 'Extraction eval', icon: Gauge, roles: ['analyst', 'curator', 'project_manager', 'admin'] },
  { id: 'qualityboard', label: 'Табло качества', icon: Activity, roles: ['analyst', 'curator', 'project_manager', 'admin'] },
  { id: 'ragchecks', label: 'RAGAS / DeepEval', icon: ShieldCheck, roles: ['analyst', 'curator', 'project_manager', 'admin'] },
  { id: 'suspects', label: 'Подозрительные значения', icon: TriangleAlert, roles: CURATOR },
  { id: 'kghealth', label: 'Здоровье графа', icon: HeartPulse, roles: CURATOR },
];

export function App() {
  const { view, setView, role, useLlm, setUseLlm, user, signOut } = useStore();
  useOidcCallback();
  const stats = useQuery({ queryKey: ['stats'], queryFn: api.stats, enabled: !!user });

  // Gate the whole app on sign-in — «красивая авторизация» first.
  if (!user) return <LoginView />;

  const nav = NAV.filter((n) => !n.roles || n.roles.includes(role));
  if (!nav.some((n) => n.id === view)) setView('chat');

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Left rail */}
      <aside className="flex w-16 shrink-0 flex-col items-center border-r border-line bg-graphite/60 py-4">
        <div className="mb-6 flex h-9 w-9 items-center justify-center rounded-md bg-copper/15 text-copper">
          <ClubokMark />
        </div>
        <nav className="flex flex-1 flex-col gap-1 overflow-y-auto">
          {nav.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setView(id)}
              title={label}
              className={`group flex h-11 w-11 flex-col items-center justify-center rounded-md transition-colors ${
                view === id ? 'bg-copper/15 text-copper' : 'text-faint hover:text-nickel'
              }`}
            >
              <Icon size={18} strokeWidth={1.75} />
            </button>
          ))}
        </nav>
        <div className="text-faint" title="OSS-only модели">
          <CircleHelp size={16} />
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
