import { Boxes, Hexagon } from 'lucide-react';
import { TabHub } from './TabHub';
import { EntityDetailView } from './EntityDetailView';
import { SimilarEmbeddingsView } from './SimilarEmbeddingsView';

// «Сущности и похожие» — единый раздел исследования графа: карточка сущности (свойства,
// соседи, история) и семантически похожие объекты.
export function GraphExploreView() {
  return (
    <TabHub
      eyebrow="граф · сущности и связи"
      tabs={[
        { id: 'entities', label: 'Карточка сущности', icon: Boxes, render: () => <EntityDetailView /> },
        { id: 'simembed', label: 'Похожие', icon: Hexagon, render: () => <SimilarEmbeddingsView /> },
      ]}
    />
  );
}
