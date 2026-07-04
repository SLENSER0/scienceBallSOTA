import { FileCode2, GitBranch, Route } from 'lucide-react';
import { TabHub } from './TabHub';
import { AgentReasoningTimelineView } from './AgentReasoningTimelineView';
import { AgentTraceView } from './AgentTraceView';
import { RunTransparencyView } from './RunTransparencyView';

// «Ход мысли ассистента» — как ассистент пришёл к ответу: таймлайн рассуждения, разбор
// по шагам и воспроизводимость прогона.
export function AgentReasoningHubView() {
  return (
    <TabHub
      eyebrow="ассистент · как получен ответ"
      tabs={[
        { id: 'reasoning', label: 'Ход мысли', icon: Route, render: () => <AgentReasoningTimelineView /> },
        { id: 'agenttrace', label: 'Разбор по шагам', icon: GitBranch, render: () => <AgentTraceView /> },
        { id: 'runtransparency', label: 'Воспроизводимость', icon: FileCode2, render: () => <RunTransparencyView /> },
      ]}
    />
  );
}
