import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Users,
  Bell,
  AtSign,
  MessageSquare,
  Loader2,
  Plus,
  Send,
  CheckCheck,
  Activity as ActivityIcon,
  Circle,
  ShieldCheck,
  FlaskConical,
  TriangleAlert,
} from 'lucide-react';

// Collaboration workspace: комментарии / @mentions / shared investigations / notification center (§23.32).
//
// Превращает read-only обозреватель графа в командный инструмент. Слева — список
// расследований (shared investigations) + создание; в центре — выбранное расследование
// с тредом комментариев, @mentions и жизненным циклом (draft/in_review/resolved/archived);
// справа — центр уведомлений (mentioned / assigned_review / evidence_corrected / gap_closed)
// и лента активности по проекту/лаборатории.
//
// Бэкенд `GET/POST/PATCH /api/v1/collab/*` — тонкая обёртка над чистым
// CollaborationStore (kg_common.storage.collaboration), та же SQLAlchemy-модель, что и
// saved-views §14.15. Комментарии НЕ считаются factual evidence без ручного promoted-статуса (§10.8).

// --------------------------------------------------------------------------- types
type Comment = {
  comment_id: string;
  target_type: string;
  target_id: string;
  author: string;
  body: string;
  status: string;
  parent_id: string;
  investigation_id: string;
  project: string;
  mentions: string[];
  promoted: boolean;
  created_at: string;
  updated_at: string;
};

type Investigation = {
  investigation_id: string;
  owner: string;
  title: string;
  notes: string;
  status: string;
  project: string;
  entities: unknown[];
  filters: Record<string, unknown>;
  view: Record<string, unknown>;
  answers: unknown[];
  members: string[];
  created_at: string;
  updated_at: string;
  comments?: Comment[];
};

type Notification = {
  notif_id: string;
  user_id: string;
  kind: string;
  text: string;
  actor: string;
  target_type: string;
  target_id: string;
  investigation_id: string;
  read: boolean;
  created_at: string;
};

type ActivityEvent = {
  activity_id: string;
  actor: string;
  verb: string;
  target_type: string;
  target_id: string;
  project: string;
  summary: string;
  created_at: string;
};

// --------------------------------------------------------------------------- fetch
function authHeaders(): Record<string, string> {
  try {
    const raw = localStorage.getItem('sb.session');
    if (raw) {
      const s = JSON.parse(raw);
      if (s?.token) return { Authorization: `Bearer ${s.token}` };
      if (s?.role) return { 'X-Role': s.role };
    }
  } catch {
    /* ignore */
  }
  return {};
}

async function cFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...authHeaders(), ...(init?.headers ?? {}) },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

// --------------------------------------------------------------------------- presentation meta
const STATUS_META: Record<string, { ru: string; rgb: string }> = {
  draft: { ru: 'черновик', rgb: '138, 148, 158' },
  in_review: { ru: 'на ревью', rgb: '184, 115, 51' },
  resolved: { ru: 'решено', rgb: '70, 167, 88' },
  archived: { ru: 'архив', rgb: '110, 118, 128' },
};
function statusMeta(s: string) {
  return STATUS_META[s] ?? STATUS_META.draft;
}

const KIND_META: Record<string, { ru: string; icon: typeof Bell }> = {
  mentioned: { ru: 'упоминание', icon: AtSign },
  assigned_review: { ru: 'назначено ревью', icon: ShieldCheck },
  evidence_corrected: { ru: 'evidence исправлено', icon: FlaskConical },
  gap_closed: { ru: 'пробел закрыт', icon: CheckCheck },
  reply: { ru: 'ответ', icon: MessageSquare },
  comment: { ru: 'комментарий', icon: MessageSquare },
};
function kindMeta(k: string) {
  return KIND_META[k] ?? { ru: k, icon: Bell };
}

function ago(iso: string): string {
  if (!iso) return '';
  const d = new Date(iso).getTime();
  if (Number.isNaN(d)) return iso.slice(0, 16).replace('T', ' ');
  const s = Math.max(0, (Date.now() - d) / 1000);
  if (s < 60) return 'только что';
  if (s < 3600) return `${Math.floor(s / 60)} мин назад`;
  if (s < 86400) return `${Math.floor(s / 3600)} ч назад`;
  return `${Math.floor(s / 86400)} дн назад`;
}

// highlight @mentions inside a comment body
function renderBody(body: string) {
  const parts = body.split(/(@[A-Za-z0-9_./:\-]+)/g);
  return parts.map((p, i) =>
    p.startsWith('@') ? (
      <span key={i} className="font-medium text-copper">
        {p}
      </span>
    ) : (
      <span key={i}>{p}</span>
    ),
  );
}

const STATUSES = ['draft', 'in_review', 'resolved', 'archived'];

// --------------------------------------------------------------------------- component
export function CollaborationView() {
  const qc = useQueryClient();
  const [selected, setSelected] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState('');
  const [newMembers, setNewMembers] = useState('');
  const [newProject, setNewProject] = useState('');
  const [draft, setDraft] = useState('');
  const [assignee, setAssignee] = useState('');

  const invListQ = useQuery({
    queryKey: ['collab-investigations'],
    queryFn: () =>
      cFetch<{ investigations: Investigation[]; count: number }>('/api/v1/collab/investigations'),
    staleTime: 30_000,
  });

  const invDetailQ = useQuery({
    queryKey: ['collab-investigation', selected],
    enabled: !!selected,
    queryFn: () =>
      cFetch<Investigation>(`/api/v1/collab/investigations/${encodeURIComponent(selected as string)}`),
    staleTime: 10_000,
  });

  const notifQ = useQuery({
    queryKey: ['collab-notifications'],
    queryFn: () =>
      cFetch<{ notifications: Notification[]; unread: number; count: number }>(
        '/api/v1/collab/notifications?limit=50',
      ),
    refetchInterval: 20_000,
  });

  const activityQ = useQuery({
    queryKey: ['collab-activity', newProject],
    queryFn: () => {
      const p = new URLSearchParams({ limit: '40' });
      if (newProject) p.set('project', newProject);
      return cFetch<{ activity: ActivityEvent[]; count: number }>(
        `/api/v1/collab/activity?${p.toString()}`,
      );
    },
    refetchInterval: 30_000,
  });

  const refetchAll = () => {
    qc.invalidateQueries({ queryKey: ['collab-investigations'] });
    qc.invalidateQueries({ queryKey: ['collab-investigation', selected] });
    qc.invalidateQueries({ queryKey: ['collab-notifications'] });
    qc.invalidateQueries({ queryKey: ['collab-activity'] });
  };

  const createInv = useMutation({
    mutationFn: () =>
      cFetch<Investigation>('/api/v1/collab/investigations', {
        method: 'POST',
        body: JSON.stringify({
          title: newTitle,
          project: newProject,
          members: newMembers
            .split(/[,\s]+/)
            .map((m) => m.trim())
            .filter(Boolean),
        }),
      }),
    onSuccess: (inv) => {
      setNewTitle('');
      setNewMembers('');
      setSelected(inv.investigation_id);
      refetchAll();
    },
  });

  const addComment = useMutation({
    mutationFn: () =>
      cFetch<Comment>('/api/v1/collab/comments', {
        method: 'POST',
        body: JSON.stringify({
          target_type: 'Investigation',
          target_id: selected,
          body: draft,
          investigation_id: selected,
          project: invDetailQ.data?.project ?? '',
        }),
      }),
    onSuccess: () => {
      setDraft('');
      refetchAll();
    },
  });

  const setCommentStatus = useMutation({
    mutationFn: (args: { id: string; status: string }) =>
      cFetch<Comment>(`/api/v1/collab/comments/${encodeURIComponent(args.id)}/status`, {
        method: 'POST',
        body: JSON.stringify({ status: args.status, assignee }),
      }),
    onSuccess: () => refetchAll(),
  });

  const setInvStatus = useMutation({
    mutationFn: (status: string) =>
      cFetch<Investigation>(
        `/api/v1/collab/investigations/${encodeURIComponent(selected as string)}`,
        { method: 'PATCH', body: JSON.stringify({ status }) },
      ),
    onSuccess: () => refetchAll(),
  });

  const markRead = useMutation({
    mutationFn: (id: string) =>
      cFetch(`/api/v1/collab/notifications/${encodeURIComponent(id)}/read`, { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['collab-notifications'] }),
  });

  const markAllRead = useMutation({
    mutationFn: () => cFetch('/api/v1/collab/notifications/read-all', { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['collab-notifications'] }),
  });

  const investigations = invListQ.data?.investigations ?? [];
  const comments = invDetailQ.data?.comments ?? [];
  const notifs = notifQ.data?.notifications ?? [];
  const unread = notifQ.data?.unread ?? 0;
  const activity = activityQ.data?.activity ?? [];

  const selectedInv = useMemo(
    () => investigations.find((i) => i.investigation_id === selected) ?? invDetailQ.data ?? null,
    [investigations, selected, invDetailQ.data],
  );

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-7xl">
        <div className="eyebrow mb-1">команда · совместная работа</div>
        <h1 className="flex items-center gap-2 font-display text-2xl font-semibold tracking-tight">
          <Users size={22} className="text-copper" /> Совместные расследования
        </h1>
        <p className="mt-1 max-w-3xl text-sm text-faint">
          Комментарии к узлам графа, @mentions, общие «investigation»-воркспейсы и центр
          уведомлений. Два исследователя могут вместе разобрать противоречие или пробел, оставить
          комментарии, назначить action и сохранить расследование. Комментарии не считаются
          доказательством без ручного promoted-статуса (§10.8).
        </p>

        <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-[280px_1fr_300px]">
          {/* ---------------------------------------------------------- investigations */}
          <div className="flex flex-col gap-3">
            <div className="panel px-3 py-3">
              <div className="mb-2 flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-wide text-faint">
                <Plus size={13} className="text-copper" /> новое расследование
              </div>
              <input
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                placeholder="название"
                className="mb-2 w-full rounded border border-line/60 bg-transparent px-2 py-1 text-[12px] text-ink outline-none placeholder:text-faint"
              />
              <input
                value={newProject}
                onChange={(e) => setNewProject(e.target.value)}
                placeholder="проект / лаборатория"
                className="mb-2 w-full rounded border border-line/60 bg-transparent px-2 py-1 text-[12px] text-ink outline-none placeholder:text-faint"
              />
              <input
                value={newMembers}
                onChange={(e) => setNewMembers(e.target.value)}
                placeholder="участники (через запятую)"
                className="mb-2 w-full rounded border border-line/60 bg-transparent px-2 py-1 text-[12px] text-ink outline-none placeholder:text-faint"
              />
              <button
                disabled={!newTitle.trim() || createInv.isPending}
                onClick={() => createInv.mutate()}
                className="flex w-full items-center justify-center gap-1.5 rounded bg-copper/15 px-2 py-1.5 font-mono text-[11px] text-copper transition-colors hover:bg-copper/25 disabled:opacity-40"
              >
                {createInv.isPending ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}
                создать
              </button>
            </div>

            <div className="panel overflow-hidden">
              <div className="border-b border-line/40 px-3 py-2 font-mono text-[11px] text-faint">
                расследований: {investigations.length}
              </div>
              <div className="max-h-[520px] overflow-y-auto">
                {invListQ.isLoading ? (
                  <div className="flex items-center gap-2 px-3 py-4 font-mono text-[11px] text-faint">
                    <Loader2 size={13} className="animate-spin text-copper" /> загрузка…
                  </div>
                ) : investigations.length === 0 ? (
                  <div className="px-3 py-6 text-center font-mono text-[11px] text-faint">
                    пока нет расследований — создайте первое
                  </div>
                ) : (
                  investigations.map((inv) => {
                    const sm = statusMeta(inv.status);
                    const active = inv.investigation_id === selected;
                    return (
                      <button
                        key={inv.investigation_id}
                        onClick={() => setSelected(inv.investigation_id)}
                        className={`block w-full border-t border-line/30 px-3 py-2 text-left transition-colors ${
                          active ? 'bg-copper/10' : 'hover:bg-line/10'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="truncate text-[12px] font-medium text-ink">
                            {inv.title}
                          </span>
                          <span
                            className="shrink-0 rounded px-1.5 py-0.5 font-mono text-[9px]"
                            style={{ color: `rgb(${sm.rgb})`, background: `rgba(${sm.rgb},0.12)` }}
                          >
                            {sm.ru}
                          </span>
                        </div>
                        <div className="mt-0.5 flex items-center gap-2 font-mono text-[10px] text-faint">
                          <span>{inv.owner}</span>
                          {inv.members.length > 0 && <span>+{inv.members.length}</span>}
                          {inv.project && <span>· {inv.project}</span>}
                        </div>
                      </button>
                    );
                  })
                )}
              </div>
            </div>
          </div>

          {/* ---------------------------------------------------------- investigation detail + thread */}
          <div className="panel flex min-h-[560px] flex-col px-4 py-4">
            {!selectedInv ? (
              <div className="flex flex-1 items-center justify-center text-center font-mono text-[11px] text-faint">
                выберите расследование слева, чтобы открыть тред комментариев
              </div>
            ) : (
              <>
                <div className="flex items-start justify-between gap-3 border-b border-line/40 pb-3">
                  <div>
                    <div className="eyebrow mb-0.5">
                      {selectedInv.project || 'без проекта'} · владелец {selectedInv.owner}
                    </div>
                    <div className="font-display text-lg font-semibold text-ink">
                      {selectedInv.title}
                    </div>
                    {selectedInv.members.length > 0 && (
                      <div className="mt-0.5 font-mono text-[10px] text-faint">
                        участники: {selectedInv.members.join(', ')}
                      </div>
                    )}
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <div className="flex flex-wrap justify-end gap-1">
                      {STATUSES.map((s) => {
                        const sm = statusMeta(s);
                        const on = selectedInv.status === s;
                        return (
                          <button
                            key={s}
                            onClick={() => setInvStatus.mutate(s)}
                            className="rounded px-1.5 py-0.5 font-mono text-[9px] transition-colors"
                            style={{
                              color: on ? `rgb(${sm.rgb})` : 'inherit',
                              background: on ? `rgba(${sm.rgb},0.15)` : 'transparent',
                              border: `1px solid rgba(${sm.rgb},${on ? 0.6 : 0.25})`,
                            }}
                          >
                            {sm.ru}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>

                {/* comment thread */}
                <div className="mt-3 flex-1 space-y-3 overflow-y-auto pr-1">
                  {invDetailQ.isLoading ? (
                    <div className="flex items-center gap-2 font-mono text-[11px] text-faint">
                      <Loader2 size={13} className="animate-spin text-copper" /> загрузка треда…
                    </div>
                  ) : comments.length === 0 ? (
                    <div className="py-10 text-center font-mono text-[11px] text-faint">
                      комментариев пока нет — начните обсуждение ниже
                    </div>
                  ) : (
                    comments.map((c) => {
                      const sm = statusMeta(c.status);
                      return (
                        <div
                          key={c.comment_id}
                          className={`rounded-md border border-line/40 px-3 py-2 ${
                            c.parent_id ? 'ml-6' : ''
                          }`}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-mono text-[11px] font-medium text-ink">
                              {c.author}
                            </span>
                            <span className="font-mono text-[10px] text-faint">
                              {ago(c.created_at)}
                            </span>
                          </div>
                          <div className="mt-1 whitespace-pre-wrap text-[12px] text-ink">
                            {renderBody(c.body)}
                          </div>
                          <div className="mt-2 flex flex-wrap items-center gap-1.5">
                            <span
                              className="rounded px-1.5 py-0.5 font-mono text-[9px]"
                              style={{ color: `rgb(${sm.rgb})`, background: `rgba(${sm.rgb},0.12)` }}
                            >
                              {sm.ru}
                            </span>
                            {c.promoted && (
                              <span className="rounded bg-copper/15 px-1.5 py-0.5 font-mono text-[9px] text-copper">
                                promoted evidence
                              </span>
                            )}
                            {c.mentions
                              .filter((m) => !m.startsWith('lab:'))
                              .map((m) => (
                                <span key={m} className="font-mono text-[9px] text-copper">
                                  @{m}
                                </span>
                              ))}
                            <span className="mx-1 h-3 w-px bg-line/40" />
                            {STATUSES.filter((s) => s !== c.status).map((s) => (
                              <button
                                key={s}
                                onClick={() => setCommentStatus.mutate({ id: c.comment_id, status: s })}
                                className="rounded px-1.5 py-0.5 font-mono text-[9px] text-faint transition-colors hover:bg-line/20 hover:text-ink"
                              >
                                → {statusMeta(s).ru}
                              </button>
                            ))}
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>

                {/* composer */}
                <div className="mt-3 border-t border-line/40 pt-3">
                  <div className="mb-2 flex items-center gap-2">
                    <AtSign size={12} className="text-faint" />
                    <input
                      value={assignee}
                      onChange={(e) => setAssignee(e.target.value)}
                      placeholder="assignee для «на ревью» (опц.)"
                      className="flex-1 rounded border border-line/50 bg-transparent px-2 py-1 font-mono text-[10px] text-ink outline-none placeholder:text-faint"
                    />
                  </div>
                  <div className="flex items-end gap-2">
                    <textarea
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      placeholder="комментарий… используйте @имя для упоминания"
                      rows={2}
                      className="flex-1 resize-none rounded border border-line/60 bg-transparent px-2 py-1.5 text-[12px] text-ink outline-none placeholder:text-faint"
                    />
                    <button
                      disabled={!draft.trim() || addComment.isPending}
                      onClick={() => addComment.mutate()}
                      className="flex items-center gap-1.5 rounded bg-copper/15 px-3 py-2 font-mono text-[11px] text-copper transition-colors hover:bg-copper/25 disabled:opacity-40"
                    >
                      {addComment.isPending ? (
                        <Loader2 size={13} className="animate-spin" />
                      ) : (
                        <Send size={13} />
                      )}
                      отправить
                    </button>
                  </div>
                </div>
              </>
            )}
          </div>

          {/* ---------------------------------------------------------- notifications + activity */}
          <div className="flex flex-col gap-3">
            <div className="panel overflow-hidden">
              <div className="flex items-center justify-between border-b border-line/40 px-3 py-2">
                <span className="flex items-center gap-1.5 font-mono text-[11px] text-faint">
                  <Bell size={13} className="text-copper" /> уведомления
                  {unread > 0 && (
                    <span className="rounded-full bg-copper px-1.5 py-0.5 text-[9px] font-bold text-black">
                      {unread}
                    </span>
                  )}
                </span>
                {unread > 0 && (
                  <button
                    onClick={() => markAllRead.mutate()}
                    className="flex items-center gap-1 font-mono text-[10px] text-faint transition-colors hover:text-ink"
                  >
                    <CheckCheck size={12} /> все
                  </button>
                )}
              </div>
              <div className="max-h-[300px] overflow-y-auto">
                {notifQ.isLoading ? (
                  <div className="flex items-center gap-2 px-3 py-4 font-mono text-[11px] text-faint">
                    <Loader2 size={13} className="animate-spin text-copper" /> загрузка…
                  </div>
                ) : notifs.length === 0 ? (
                  <div className="px-3 py-6 text-center font-mono text-[11px] text-faint">
                    уведомлений нет
                  </div>
                ) : (
                  notifs.map((n) => {
                    const km = kindMeta(n.kind);
                    const Icon = km.icon;
                    return (
                      <button
                        key={n.notif_id}
                        onClick={() => !n.read && markRead.mutate(n.notif_id)}
                        className={`flex w-full items-start gap-2 border-t border-line/30 px-3 py-2 text-left transition-colors hover:bg-line/10 ${
                          n.read ? 'opacity-55' : ''
                        }`}
                      >
                        <Icon size={13} className="mt-0.5 shrink-0 text-copper" />
                        <div className="min-w-0 flex-1">
                          <div className="text-[11px] text-ink">{n.text}</div>
                          <div className="mt-0.5 flex items-center gap-2 font-mono text-[9px] text-faint">
                            <span>{km.ru}</span>
                            <span>· {ago(n.created_at)}</span>
                          </div>
                        </div>
                        {!n.read && <Circle size={7} className="mt-1 shrink-0 fill-copper text-copper" />}
                      </button>
                    );
                  })
                )}
              </div>
            </div>

            <div className="panel overflow-hidden">
              <div className="flex items-center gap-1.5 border-b border-line/40 px-3 py-2 font-mono text-[11px] text-faint">
                <ActivityIcon size={13} className="text-copper" /> лента активности
                {newProject && <span>· {newProject}</span>}
              </div>
              <div className="max-h-[280px] overflow-y-auto">
                {activityQ.isLoading ? (
                  <div className="flex items-center gap-2 px-3 py-4 font-mono text-[11px] text-faint">
                    <Loader2 size={13} className="animate-spin text-copper" /> загрузка…
                  </div>
                ) : activity.length === 0 ? (
                  <div className="px-3 py-6 text-center font-mono text-[11px] text-faint">
                    активности нет
                  </div>
                ) : (
                  activity.map((a) => (
                    <div key={a.activity_id} className="border-t border-line/30 px-3 py-2">
                      <div className="text-[11px] text-ink">
                        <span className="font-medium text-copper">{a.actor}</span> {a.summary}
                      </div>
                      <div className="mt-0.5 font-mono text-[9px] text-faint">
                        {a.target_type} {a.target_id} · {ago(a.created_at)}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>

            {(invListQ.isError || notifQ.isError) && (
              <div
                className="panel flex items-center gap-2 px-3 py-3 font-mono text-[11px]"
                style={{ color: '#E5484D' }}
              >
                <TriangleAlert size={14} /> сервис совместной работы недоступен
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
