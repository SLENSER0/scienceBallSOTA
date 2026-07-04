import { Boxes, Hexagon, History } from 'lucide-react';
import { TabHub } from './TabHub';
import { EntityDetailView } from './EntityDetailView';
import { SimilarEmbeddingsView } from './SimilarEmbeddingsView';
import { EntityTimelineView } from './EntityTimelineView';

// «Сущности и похожие» — единый раздел исследования графа: карточка сущности (свойства,
// соседи, история), семантически похожие объекты и временная шкала накопления знания.
export function GraphExploreView() {
  return (
    <TabHub
      eyebrow="граф · сущности и связи"
      tabs={[
        { id: 'entities', label: 'Карточка сущности', icon: Boxes, render: () => <EntityDetailView /> },
        { id: 'simembed', label: 'Похожие', icon: Hexagon, render: () => <SimilarEmbeddingsView /> },
        { id: 'entitytimeline', label: 'История сущности', icon: History, render: () => <EntityTimelineView /> },
      ]}
    />
  );
}
