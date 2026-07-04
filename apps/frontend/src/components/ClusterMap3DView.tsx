import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';

/**
 * Corpus topic map — interactive 3D scatter of the chunk-embedding space.
 *
 * Fetches GET /api/v1/cluster-map (spherical K-Means clusters + numpy PCA-3D coords +
 * term labels, computed over the Qdrant :Chunk vectors) and renders it as a rotatable
 * point cloud on a raw <canvas> — no heavy 3D bundle. Drag to rotate, wheel to zoom,
 * hover a point for its chunk text, click a legend row to isolate a cluster.
 */

type Point = { x: number; y: number; z: number; c: number; t: string };
type Cluster = { id: number; label: string; terms: string[]; size: number; pct: number };
type MapData = {
  points: Point[];
  clusters: Cluster[];
  total: number;
  shown: number;
  var3d: number;
  k: number;
};

// 12 vivid, well-separated hues tuned for the dark viewport (position is primary,
// hover + legend give unambiguous identity, so color is a grouping aid).
const PALETTE = [
  '#4b9fff', '#2ec4a6', '#f2c14e', '#5cc85c', '#a98bf5', '#f56b8a',
  '#f2884b', '#d69a3f', '#6b8cff', '#ef5350', '#4dd0d8', '#b06fd6',
];
const colorOf = (c: number) => PALETTE[c % PALETTE.length];

function authHeaders(): Record<string, string> {
  try {
    const s = JSON.parse(localStorage.getItem('sb.session') || 'null');
    if (s?.token) return { Authorization: `Bearer ${s.token}` };
    if (s?.role) return { 'X-Role': s.role };
  } catch {
    /* no session */
  }
  return {};
}

export function ClusterMap3DView() {
  const [data, setData] = useState<MapData | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [hidden, setHidden] = useState<Set<number>>(new Set());
  const [solo, setSolo] = useState<number>(-1);
  const [spin, setSpin] = useState(true);
  const [tip, setTip] = useState<{ x: number; y: number; c: number; label: string; text: string } | null>(null);

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  // Mutable view state kept off React so the animation loop never triggers re-render.
  const view = useRef({ rotY: 0.6, rotX: -0.35, zoom: 1 });
  const spinRef = useRef(spin);
  const hiddenRef = useRef(hidden);
  const soloRef = useRef(solo);
  spinRef.current = spin;
  hiddenRef.current = hidden;
  soloRef.current = solo;

  useEffect(() => {
    let alive = true;
    fetch('/api/v1/cluster-map', { headers: { ...authHeaders() } })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((d: MapData) => {
        if (alive) setData(d);
      })
      .catch((e) => alive && setErr(String(e)));
    return () => {
      alive = false;
    };
  }, []);

  const active = useMemo(
    () => (c: number) => (soloRef.current >= 0 ? c === soloRef.current : !hiddenRef.current.has(c)),
    [],
  );

  // Render loop + interaction — set up once data arrives.
  useEffect(() => {
    const cv = canvasRef.current;
    if (!cv || !data) return;
    const ctx = cv.getContext('2d');
    if (!ctx) return;
    const P = data.points;
    const scr = new Float32Array(P.length * 2);
    const dep = new Float32Array(P.length);
    const order = Array.from(P.keys());
    let W = 0, H = 0, cx = 0, cy = 0, scl = 0, raf = 0;

    const resize = () => {
      const dpr = Math.min(2, devicePixelRatio || 1);
      const rect = cv.getBoundingClientRect();
      W = rect.width; H = rect.height;
      cv.width = W * dpr; cv.height = H * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      cx = W / 2; cy = H / 2; scl = Math.min(W, H) * 0.36;
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(cv);

    const project = () => {
      const v = view.current;
      const cyv = Math.cos(v.rotY), sy = Math.sin(v.rotY);
      const cxv = Math.cos(v.rotX), sx = Math.sin(v.rotX);
      for (let i = 0; i < P.length; i++) {
        const p = P[i];
        const x1 = p.x * cyv + p.z * sy;
        const z1 = -p.x * sy + p.z * cyv;
        const y1 = p.y * cxv - z1 * sx;
        const z2 = p.y * sx + z1 * cxv;
        const persp = 1 / (2.4 - z2 * 0.9);
        scr[i * 2] = cx + x1 * scl * v.zoom * persp * 2.4;
        scr[i * 2 + 1] = cy + y1 * scl * v.zoom * persp * 2.4;
        dep[i] = z2;
      }
      order.sort((a, b) => dep[a] - dep[b]);
    };
    const draw = () => {
      ctx.fillStyle = '#0a0c10';
      ctx.fillRect(0, 0, W, H);
      for (let k = 0; k < order.length; k++) {
        const i = order[k], c = P[i].c;
        if (!active(c)) continue;
        const sxp = scr[i * 2], syp = scr[i * 2 + 1];
        if (sxp < -20 || sxp > W + 20 || syp < -20 || syp > H + 20) continue;
        const t = (dep[i] + 1.4) / 2.8;
        ctx.globalAlpha = 0.28 + 0.62 * t;
        ctx.fillStyle = colorOf(c);
        ctx.beginPath();
        ctx.arc(sxp, syp, 1.5 + 2.6 * t, 0, 6.283);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
    };
    const frame = () => {
      if (spinRef.current) view.current.rotY += 0.0022;
      project();
      draw();
      raf = requestAnimationFrame(frame);
    };
    frame();

    // interaction
    let drag = false, pxp = 0, pyp = 0;
    const down = (e: PointerEvent) => { drag = true; pxp = e.clientX; pyp = e.clientY; cv.setPointerCapture(e.pointerId); };
    const up = () => { drag = false; };
    const move = (e: PointerEvent) => {
      if (drag) {
        view.current.rotY += (e.clientX - pxp) * 0.006;
        view.current.rotX = Math.max(-1.5, Math.min(1.5, view.current.rotX + (e.clientY - pyp) * 0.006));
        pxp = e.clientX; pyp = e.clientY; setTip(null);
        return;
      }
      const rect = cv.getBoundingClientRect();
      const mx = e.clientX - rect.left, my = e.clientY - rect.top;
      let best = -1, bd = 90;
      for (let k = order.length - 1; k >= 0; k--) {
        const i = order[k]; if (!active(P[i].c)) continue;
        const dx = scr[i * 2] - mx, dy = scr[i * 2 + 1] - my, dd = dx * dx + dy * dy;
        if (dd < bd) { bd = dd; best = i; }
      }
      if (best < 0) { setTip(null); return; }
      const p = P[best];
      setTip({ x: e.clientX, y: e.clientY, c: p.c, label: data.clusters[p.c].label, text: p.t });
    };
    const wheel = (e: WheelEvent) => {
      e.preventDefault();
      view.current.zoom = Math.max(0.4, Math.min(6, view.current.zoom * (e.deltaY < 0 ? 1.1 : 0.9)));
    };
    cv.addEventListener('pointerdown', down);
    cv.addEventListener('pointerup', up);
    cv.addEventListener('pointermove', move);
    cv.addEventListener('pointerleave', () => setTip(null));
    cv.addEventListener('wheel', wheel, { passive: false });
    return () => {
      cancelAnimationFrame(raf); ro.disconnect();
      cv.removeEventListener('pointerdown', down);
      cv.removeEventListener('pointerup', up);
      cv.removeEventListener('pointermove', move);
      cv.removeEventListener('wheel', wheel);
    };
  }, [data, active]);

  const toggle = (id: number) => {
    if (soloRef.current >= 0) { setSolo(id === soloRef.current ? -1 : id); return; }
    setHidden((h) => {
      const n = new Set(h);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  };
  const reset = () => {
    view.current = { rotY: 0.6, rotX: -0.35, zoom: 1 };
    setHidden(new Set()); setSolo(-1);
  };

  if (err) return <div style={{ padding: 24, color: '#e0666e' }}>Не удалось загрузить карту: {err}. Постройте её: <code>uv run python scripts/precompute_cluster_map.py</code></div>;
  if (!data) return <div style={{ padding: 24, opacity: 0.7 }}>Загрузка карты тем корпуса…</div>;

  const wrap: CSSProperties = { position: 'relative', width: '100%', height: 'calc(100vh - 96px)', minHeight: 480, borderRadius: 12, overflow: 'hidden', background: '#0a0c10' };
  const legend: CSSProperties = { position: 'absolute', top: 12, right: 12, width: 260, maxHeight: 'calc(100% - 90px)', overflow: 'auto', background: 'rgba(16,18,24,.86)', border: '1px solid #262b35', borderRadius: 10, padding: 8, backdropFilter: 'blur(8px)', color: '#e9edf3', fontSize: 12.5 };

  return (
    <div style={{ padding: '0 4px' }}>
      <div style={{ margin: '2px 0 10px' }}>
        <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>Карта тем корпуса — 3D</h2>
        <div style={{ fontSize: 12.5, opacity: 0.7, marginTop: 2, fontVariantNumeric: 'tabular-nums' }}>
          {data.total.toLocaleString('ru')} чанков · {data.k} тематических кластеров · показано {data.shown.toLocaleString('ru')} · PCA-3D охват {data.var3d}%
        </div>
      </div>
      <div style={wrap}>
        <canvas ref={canvasRef} style={{ display: 'block', width: '100%', height: '100%', cursor: 'grab' }} />
        <div style={{ position: 'absolute', left: 12, top: 12, fontSize: 11.5, color: '#8a93a2', fontFamily: 'ui-monospace,Menlo,monospace' }}>
          перетаскивай — поворот · колесо — зум · наведи — чанк
        </div>
        <div style={legend}>
          <div style={{ fontSize: 10.5, letterSpacing: '.09em', textTransform: 'uppercase', color: '#8a93a2', fontWeight: 700, margin: '2px 4px 8px' }}>Кластеры · доля корпуса</div>
          {data.clusters.map((cl) => {
            const off = solo >= 0 ? cl.id !== solo : hidden.has(cl.id);
            return (
              <div key={cl.id} onClick={() => toggle(cl.id)} onDoubleClick={() => setSolo(solo === cl.id ? -1 : cl.id)}
                style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '5px 6px', borderRadius: 8, cursor: 'pointer', opacity: off ? 0.34 : 1 }}>
                <span style={{ width: 11, height: 11, borderRadius: 3, flex: 'none', background: colorOf(cl.id), boxShadow: 'inset 0 0 0 1px rgba(0,0,0,.3)' }} />
                <span style={{ flex: 1, lineHeight: 1.2 }}>{cl.label}
                  <small style={{ display: 'block', color: '#8a93a2', fontSize: 10.5, fontFamily: 'ui-monospace,Menlo,monospace' }}>{cl.terms.slice(0, 4).join(' · ')}</small>
                </span>
                <span style={{ fontFamily: 'ui-monospace,Menlo,monospace', fontSize: 11, color: '#8a93a2', fontVariantNumeric: 'tabular-nums' }}>{cl.pct}%</span>
              </div>
            );
          })}
        </div>
        <div style={{ position: 'absolute', left: 12, bottom: 12, display: 'flex', gap: 8 }}>
          <button onClick={() => setSpin((s) => !s)} style={btn(spin)}>{spin ? '⏸' : '▶'} вращение</button>
          <button onClick={reset} style={btn(false)}>сброс вида</button>
        </div>
        {tip && (
          <div style={{ position: 'fixed', left: Math.min(tip.x + 14, innerWidth - 320), top: tip.y + 14, zIndex: 50, maxWidth: 300, pointerEvents: 'none', background: '#12151b', border: '1px solid #262b35', borderRadius: 9, padding: '8px 10px', color: '#e9edf3', fontSize: 12.5, boxShadow: '0 4px 16px rgba(0,0,0,.5)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontWeight: 700, marginBottom: 4 }}>
              <span style={{ width: 9, height: 9, borderRadius: 2, background: colorOf(tip.c) }} />{tip.label}
            </div>
            <div style={{ color: '#aab2bf', fontSize: 11.5, lineHeight: 1.4 }}>{tip.text}</div>
          </div>
        )}
      </div>
    </div>
  );
}

function btn(on: boolean): CSSProperties {
  return {
    fontSize: 12, fontWeight: 600, padding: '7px 11px', borderRadius: 9, cursor: 'pointer',
    color: on ? '#fff' : '#e9edf3', background: on ? '#3987e5' : 'rgba(30,34,42,.9)',
    border: `1px solid ${on ? '#3987e5' : '#2a2f39'}`,
  };
}
