import { ClipboardList, GitCompareArrows, Layers, Undo2, Wrench } from 'lucide-react';
import { TabHub } from './TabHub';
import { CurationView } from './CurationView';
import { ERCandidatesView } from './ERCandidatesView';
import { MergeUndoView } from './MergeUndoView';
import { TableCorrectionView } from './TableCorrectionView';
import { CurationDiffReagraphView } from './CurationDiffReagraphView';

// «Курирование» — единый раздел работы эксперта над графом: очередь на ревью, слияние
// дубликатов, откат слияний, правка таблиц и просмотр «что изменилось» до/после.
export function CurationHubView() {
  return (
    <TabHub
      eyebrow="курирование · экспертная правка графа"
      tabs={[
        { id: 'curation', label: 'Очередь ревью', icon: ClipboardList, render: () => <CurationView /> },
        { id: 'er_candidates', label: 'Дубликаты', icon: Layers, render: () => <ERCandidatesView /> },
        { id: 'mergeundo', label: 'Откат слияний', icon: Undo2, render: () => <MergeUndoView /> },
        { id: 'tablecorrection', label: 'Правка таблиц', icon: Wrench, render: () => <TableCorrectionView /> },
        { id: 'curationdiffreagraph', label: 'Что изменилось', icon: GitCompareArrows, render: () => <CurationDiffReagraphView /> },
      ]}
    />
  );
}
