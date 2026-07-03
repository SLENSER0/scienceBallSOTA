import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight, KeyRound, Loader2, ShieldCheck, Sparkles } from 'lucide-react';
import { api } from '../api';
import { useStore } from '../store';

// «Красивая авторизация» — a branded full-screen sign-in: animated клубок hero on
// one side, an auth panel on the other. Two paths: SSO via authentik (OIDC, when
// the backend advertises it) and a local role sign-in for the demo/embedded profile.

const ROLE_META: Record<string, { title: string; blurb: string; accent: string }> = {
  admin: { title: 'Администратор', blurb: 'Полный доступ · управление и аудит', accent: '#E5484D' },
  curator: { title: 'Куратор', blurb: 'Проверка фактов · слияние · история решений', accent: '#C87941' },
  project_manager: { title: 'Руководитель', blurb: 'Покрытие · пробелы · отчёты по проекту', accent: '#6C8CD5' },
  researcher: { title: 'Исследователь', blurb: 'Запросы · граф · доказательная база', accent: '#3FB68B' },
  analyst: { title: 'Аналитик', blurb: 'Сравнение решений · технико-экономика', accent: '#E89B5C' },
  external_partner: { title: 'Внешний партнёр', blurb: 'Ограниченный доступ к публичным данным', accent: '#8FA3B0' },
};
const ROLE_ORDER = ['researcher', 'analyst', 'curator', 'project_manager', 'admin', 'external_partner'];

export function LoginView() {
  const signIn = useStore((s) => s.signIn);
  const cfg = useQuery({ queryKey: ['auth-config'], queryFn: api.authConfig, retry: 0 });
  const [username, setUsername] = useState('');
  const [role, setRole] = useState('researcher');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const roles = (cfg.data?.roles?.length ? cfg.data.roles : ROLE_ORDER)
    .slice()
    .sort((a, b) => ROLE_ORDER.indexOf(a) - ROLE_ORDER.indexOf(b));
  const oidc = cfg.data?.oidc;

  const devLogin = async () => {
    setBusy(true);
    setErr(null);
    try {
      const name = username.trim() || role;
      const res = await api.login(name, role);
      signIn(name, res.role, res.token);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  const ssoLogin = () => {
    if (!oidc?.enabled || !oidc.authorize_url) return;
    const redirect = `${window.location.origin}/`;
    const p = new URLSearchParams({
      client_id: oidc.client_id ?? 'science-ball',
      response_type: 'code',
      scope: oidc.scopes ?? 'openid profile email groups',
      redirect_uri: redirect,
    });
    window.location.href = `${oidc.authorize_url}?${p.toString()}`;
  };

  return (
    <div className="relative flex h-screen overflow-hidden bg-graphite text-ink">
      <BackdropThreads />

      {/* Hero */}
      <div className="relative z-10 hidden flex-1 flex-col justify-between p-12 lg:flex">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-copper/15 text-copper">
            <ClubokMark />
          </div>
          <span className="font-display text-lg font-semibold tracking-tight">Научный клубок</span>
        </div>
        <div className="max-w-md">
          <div className="eyebrow mb-3 text-copper-bright">Горно-металлургический R&D</div>
          <h1 className="font-display text-4xl font-semibold leading-tight tracking-tight">
            Граф знаний, которому можно доверять
          </h1>
          <p className="mt-4 text-muted">
            Единая карта решений, экспериментов и доказательств. Каждое число — со ссылкой на источник,
            каждый ответ — с оценкой достоверности.
          </p>
          <div className="mt-8 flex flex-wrap gap-2">
            {['66 027 узлов', '208 378 связей', 'OSS-only LLM', 'evidence-first'].map((t) => (
              <span key={t} className="chip text-faint">
                <Sparkles size={11} className="text-copper" /> {t}
              </span>
            ))}
          </div>
        </div>
        <div className="font-mono text-[11px] text-faint">
          Neo4j · Qdrant · OpenSearch · LangGraph · authentik SSO
        </div>
      </div>

      {/* Auth panel */}
      <div className="relative z-10 flex w-full items-center justify-center p-6 lg:w-[520px] lg:border-l lg:border-line lg:bg-surface/40 lg:backdrop-blur">
        <div className="w-full max-w-sm animate-rise">
          <div className="mb-1 flex items-center gap-2 lg:hidden">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-copper/15 text-copper">
              <ClubokMark />
            </div>
            <span className="font-display font-semibold">Научный клубок</span>
          </div>
          <h2 className="font-display text-2xl font-semibold tracking-tight">Вход</h2>
          <p className="mt-1 text-sm text-faint">Выберите способ авторизации.</p>

          {/* SSO */}
          <button
            onClick={ssoLogin}
            disabled={!oidc?.enabled}
            className={`mt-6 flex w-full items-center justify-center gap-2.5 rounded-lg px-4 py-3 text-sm font-medium transition ${
              oidc?.enabled
                ? 'bg-copper text-graphite hover:bg-copper-bright'
                : 'cursor-not-allowed border border-line bg-surface/60 text-faint'
            }`}
            title={oidc?.enabled ? 'Единый вход через authentik' : 'SSO не настроен (задайте OIDC_ISSUER)'}
          >
            <ShieldCheck size={16} />
            Войти через authentik (SSO)
            {oidc?.enabled && <ArrowRight size={15} className="ml-auto" />}
          </button>

          <div className="my-5 flex items-center gap-3 text-[11px] uppercase tracking-wider text-faint">
            <span className="h-px flex-1 bg-line" /> или как роль <span className="h-px flex-1 bg-line" />
          </div>

          {/* Role picker */}
          <div className="grid grid-cols-2 gap-2">
            {roles.map((r) => {
              const m = ROLE_META[r] ?? { title: r, blurb: '', accent: '#8FA3B0' };
              const active = role === r;
              return (
                <button
                  key={r}
                  onClick={() => setRole(r)}
                  className={`rounded-lg border p-2.5 text-left transition ${
                    active ? 'border-copper/60 bg-copper/10' : 'border-line bg-surface/40 hover:border-line/80'
                  }`}
                >
                  <div className="flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full" style={{ background: m.accent }} />
                    <span className="text-xs font-medium text-ink">{m.title}</span>
                  </div>
                  <div className="mt-0.5 text-[10px] leading-tight text-faint">{m.blurb}</div>
                </button>
              );
            })}
          </div>

          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && void devLogin()}
            placeholder="Имя пользователя (необязательно)"
            className="mt-3 w-full rounded-lg border border-line bg-surface/60 px-3 py-2.5 text-sm text-ink outline-none placeholder:text-faint focus:border-copper/50"
          />

          <button
            onClick={() => void devLogin()}
            disabled={busy}
            className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg border border-copper/40 bg-copper/10 px-4 py-3 text-sm font-medium text-copper transition hover:bg-copper/20 disabled:opacity-50"
          >
            {busy ? <Loader2 size={16} className="animate-spin" /> : <KeyRound size={16} />}
            Продолжить как {ROLE_META[role]?.title ?? role}
          </button>

          {err && <div className="mt-3 text-xs text-contradiction">{err}</div>}
          <p className="mt-5 text-center text-[11px] text-faint">
            Все компоненты — open-source. Роли и доступ разграничены (§19 RBAC).
          </p>
        </div>
      </div>
    </div>
  );
}

// Slowly drifting тред-lines behind the panel — the "клубок" motif.
function BackdropThreads() {
  return (
    <svg className="absolute inset-0 h-full w-full opacity-[0.14]" preserveAspectRatio="xMidYMid slice">
      <defs>
        <radialGradient id="lg" cx="30%" cy="40%" r="70%">
          <stop offset="0%" stopColor="#C87941" stopOpacity="0.5" />
          <stop offset="100%" stopColor="#C87941" stopOpacity="0" />
        </radialGradient>
      </defs>
      <rect width="100%" height="100%" fill="url(#lg)" />
      {Array.from({ length: 7 }).map((_, i) => (
        <circle
          key={i}
          cx="30%"
          cy="42%"
          r={70 + i * 46}
          fill="none"
          stroke="#C87941"
          strokeWidth="1"
          className="animate-thread"
          style={{ animationDelay: `${i * 0.4}s` }}
        />
      ))}
    </svg>
  );
}

function ClubokMark() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
      <circle cx="10" cy="10" r="7" stroke="currentColor" strokeWidth="1.1" opacity="0.5" />
      <path d="M4 10c3-4 9-4 12 0M4 10c3 4 9 4 12 0M10 3v14" stroke="currentColor" strokeWidth="1.1" />
    </svg>
  );
}

// After an OIDC redirect authentik returns to '/?code=...'. If a code is present
// and we have no session, surface it so the user can complete SSO (token exchange
// is a backend concern; here we just capture the round-trip state).
export function useOidcCallback() {
  const signIn = useStore((s) => s.signIn);
  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    const token = p.get('id_token') || p.get('access_token');
    if (token) {
      // authentik implicit-style return with a token in the query → adopt it.
      signIn('sso-user', 'researcher', token);
      window.history.replaceState({}, '', '/');
    }
  }, [signIn]);
}
