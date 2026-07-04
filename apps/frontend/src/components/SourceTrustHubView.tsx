import { Fingerprint, ShieldCheck } from 'lucide-react';
import { TabHub } from './TabHub';
import { SourceTrustView } from './SourceTrustView';
import { ProvenanceCitationsView } from './ProvenanceCitationsView';

// «Доверие к источникам» — можно ли верить источнику: репутация/отзыв/свежесть и
// происхождение цитаты (кто, какая лаборатория, версия, когда).
export function SourceTrustHubView() {
  return (
    <TabHub
      eyebrow="источники · доверие и происхождение"
      tabs={[
        { id: 'sourcetrust', label: 'Доверие к источнику', icon: ShieldCheck, render: () => <SourceTrustView /> },
        { id: 'provcitations', label: 'Происхождение цитат', icon: Fingerprint, render: () => <ProvenanceCitationsView /> },
      ]}
    />
  );
}
