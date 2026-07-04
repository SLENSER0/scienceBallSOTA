import { Image as ImageIcon, MapPin, Quote } from 'lucide-react';
import { TabHub } from './TabHub';
import { EvidenceBboxView } from './EvidenceBboxView';
import { FigureEvidenceView } from './FigureEvidenceView';
import { FigureCaptionEvidenceView } from './FigureCaptionEvidenceView';

// «Инспектор доказательств» — единый раздел просмотра доказательной базы факта: точная
// цитата на странице скана, фигуры и подписи рисунков как evidence. (Вкладка «Цепочка
// доверия» убрана — see-also: раздел ведёт прямо к цитате/фигурам.)
export function EvidenceInspectorHubView() {
  return (
    <TabHub
      eyebrow="доказательства · происхождение факта"
      tabs={[
        { id: 'evidencebbox', label: 'Цитата на странице', icon: MapPin, render: () => <EvidenceBboxView /> },
        { id: 'figures', label: 'Фигуры', icon: ImageIcon, render: () => <FigureEvidenceView /> },
        { id: 'figcaptions', label: 'Подписи рисунков', icon: Quote, render: () => <FigureCaptionEvidenceView /> },
      ]}
    />
  );
}
