import { Fingerprint, Image as ImageIcon, MapPin, Quote } from 'lucide-react';
import { TabHub } from './TabHub';
import { EvidenceInspectorView } from './EvidenceInspectorView';
import { EvidenceBboxView } from './EvidenceBboxView';
import { FigureEvidenceView } from './FigureEvidenceView';
import { FigureCaptionEvidenceView } from './FigureCaptionEvidenceView';

// «Инспектор доказательств» — единый раздел просмотра доказательной базы факта: цепочка
// происхождения, точная цитата на странице скана, фигуры и подписи рисунков как evidence.
export function EvidenceInspectorHubView() {
  return (
    <TabHub
      eyebrow="доказательства · происхождение факта"
      tabs={[
        { id: 'evidenceinspector', label: 'Цепочка доверия', icon: Fingerprint, render: () => <EvidenceInspectorView /> },
        { id: 'evidencebbox', label: 'Цитата на странице', icon: MapPin, render: () => <EvidenceBboxView /> },
        { id: 'figures', label: 'Фигуры', icon: ImageIcon, render: () => <FigureEvidenceView /> },
        { id: 'figcaptions', label: 'Подписи рисунков', icon: Quote, render: () => <FigureCaptionEvidenceView /> },
      ]}
    />
  );
}
