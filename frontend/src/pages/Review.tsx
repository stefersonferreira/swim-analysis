import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import CalibrationPanel, { nextPick, type Pick } from "../components/CalibrationPanel";
import FrameView from "../components/FrameView";
import MetricsPanel from "../components/MetricsPanel";
import RaceFields from "../components/RaceFields";
import Timeline, { nearestFrame } from "../components/Timeline";
import LiveOverlay from "../overlay/LiveOverlay";
import type { OverlayTimeline } from "../overlay/state";
import { EVENT_COLOR, EVENT_KEY, EVENT_LABEL, STROKE_LABEL, fmtTime } from "../labels";
import type {
  Alert,
  Anchor,
  AnchorResult,
  EventType,
  GridLine,
  Metric,
  PoolProfile,
  RaceInfo,
  ReviewState,
  SwimEvent,
  TrajectoryData,
  Video,
} from "../types";

const RATES = [0.25, 0.5, 1, 2];
const KEY_TO_TYPE: Record<string, EventType> = Object.fromEntries(
  Object.entries(EVENT_KEY).map(([type, key]) => [key.toLowerCase(), type as EventType]),
);
/** Perfil padrão a partir da prova: bandeirolas a 5 m e boias a 15 m de cada parede. */
export function defaultPool(race: RaceInfo): PoolProfile {
  const L = race.pool_length;
  const marks = [5, L - 15, 15, L - 5]
    .filter((m, i, a) => m > 0 && m < L && a.indexOf(m) === i)
    .sort((x, y) => x - y);
  return { name: `Piscina ${L} m`, length_m: L, lanes: 8, lane_width_m: 2.5, marks_m: marks };
}

type Mode = "review" | "calibration";

export default function Review({ videoId }: { videoId: string }) {
  const [video, setVideo] = useState<Video | null>(null);
  const [pts, setPts] = useState<number[]>([]);
  const [waveform, setWaveform] = useState<{ bins_per_s: number; peaks: number[] } | null>(null);
  const [frame, setFrame] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [rate, setRate] = useState(1);
  const [events, setEvents] = useState<SwimEvent[]>([]);
  const [metrics, setMetrics] = useState<Metric[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [race, setRace] = useState<RaceInfo | null>(null);
  const [selectedId, setSelectedIdState] = useState<string | null>(null);
  // Espelho síncrono da seleção: cliques rápidos não podem ver um valor antigo.
  const selectedRef = useRef<string | null>(null);
  const setSelectedId = useCallback((id: string | null) => {
    selectedRef.current = id;
    setSelectedIdState(id);
  }, []);
  const [cycleType, setCycleType] = useState<EventType>("stroke");
  const [markM, setMarkM] = useState(15);
  const [zoom, setZoom] = useState(1);
  const [showGrid, setShowGrid] = useState(true);
  const [mode, setMode] = useState<Mode>("review");
  const [error, setError] = useState<string | null>(null);
  const [editRace, setEditRace] = useState(false);
  // calibração
  const [pool, setPool] = useState<PoolProfile | null>(null);
  const [anchors, setAnchors] = useState<Anchor[]>([]);
  const [results, setResults] = useState<AnchorResult[]>([]);
  const [grids, setGrids] = useState<Record<string, GridLine[]>>({});
  const [pick, setPick] = useState<Pick>({ rope: 0, x: 0 });
  const [calDirty, setCalDirty] = useState(false);
  const [calBusy, setCalBusy] = useState(false);
  const [calMsg, setCalMsg] = useState<string | null>(null);
  // análise automática
  const [traj, setTraj] = useState<TrajectoryData | null>(null);
  const [frameGrid, setFrameGrid] = useState<GridLine[] | null>(null);
  const gridCache = useRef(new Map<number, GridLine[]>());
  // sobreposição ao vivo (Fluxi Swim)
  const [overlay, setOverlay] = useState<OverlayTimeline | null>(null);
  const [showOverlay, setShowOverlay] = useState(true);
  const [present, setPresent] = useState(false);
  const frameBox = useRef<HTMLDivElement>(null);

  const videoRef = useRef<HTMLVideoElement>(null);
  const reverseTimer = useRef<number | null>(null);

  const apply = useCallback((s: ReviewState) => {
    setEvents(s.events);
    setMetrics(s.metrics);
    setAlerts(s.alerts);
    setRace(s.race);
  }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const v = await api.getVideo(videoId);
        if (!alive) return;
        setVideo(v);
        const [f, wf, st, cal, tr] = await Promise.all([
          api.frames(videoId),
          api.waveform(videoId),
          api.events(videoId),
          api.calibration(videoId),
          api.trajectory(videoId),
        ]);
        if (!alive) return;
        setTraj(Array.isArray(tr.frames) ? null : tr.frames);
        setPts(f.pts);
        setWaveform(wf);
        apply(st);
        setPool(cal.calibration.anchors.length ? cal.calibration.pool : defaultPool(st.race));
        setAnchors(cal.calibration.anchors);
        setResults(cal.calibration.results);
        setGrids(cal.grids);
      } catch (e) {
        if (alive) setError(String((e as Error).message));
      }
    })();
    return () => {
      alive = false;
    };
  }, [videoId, apply]);

  useEffect(() => {
    if (!video || video.status !== "ready") return;
    const id = window.setTimeout(() => {
      api.overlay(videoId).then(setOverlay).catch(() => setOverlay(null));
    }, 250);
    return () => window.clearTimeout(id);
  }, [videoId, video, events]);

  const togglePresent = useCallback(async () => {
    const el = frameBox.current;
    if (!present) {
      setPresent(true);
      setShowOverlay(true);
      try {
        await el?.requestFullscreen?.();
      } catch {
        /* sem tela cheia (ex.: navegador bloqueou): fica só o modo limpo */
      }
    } else {
      setPresent(false);
      if (document.fullscreenElement) await document.exitFullscreen();
    }
  }, [present]);

  useEffect(() => {
    const h = () => {
      if (!document.fullscreenElement) setPresent(false);
    };
    document.addEventListener("fullscreenchange", h);
    return () => document.removeEventListener("fullscreenchange", h);
  }, []);

  // ---- Análise automática -----------------------------------------------------------
  const analysisActive =
    video?.analysis_status === "queued" || video?.analysis_status === "running";

  const refreshAnalysis = useCallback(async () => {
    apply(await api.events(videoId));
    const t = await api.trajectory(videoId);
    setTraj(Array.isArray(t.frames) ? null : t.frames);
    gridCache.current.clear();
    setFrameGrid(null);
  }, [videoId, apply]);

  const onVideo = useCallback(
    (v: Video) => {
      const was = video?.analysis_status;
      setVideo(v);
      if (v.analysis_status === "done" && was !== "done") void refreshAnalysis();
    },
    [video, refreshAnalysis],
  );

  useEffect(() => {
    if (!analysisActive) return;
    const id = window.setInterval(async () => {
      try {
        const v = await api.getVideo(videoId);
        setVideo(v);
        if (v.analysis_status !== "queued" && v.analysis_status !== "running") {
          await refreshAnalysis();
        }
      } catch {
        /* tenta de novo no próximo ciclo */
      }
    }, 2000);
    return () => window.clearInterval(id);
  }, [analysisActive, videoId, refreshAnalysis]);

  const runAnalysis = async () => {
    try {
      onVideo(await api.analyze(videoId));
    } catch (e) {
      setError(String((e as Error).message));
    }
  };

  const n = pts.length;
  const fps = video?.meta?.fps_measured || 30;
  const selected = events.find((e) => e.id === selectedId) ?? null;

  // ---- Reprodução -------------------------------------------------------------------
  const stopReverse = () => {
    if (reverseTimer.current) window.clearInterval(reverseTimer.current);
    reverseTimer.current = null;
  };

  const seek = useCallback(
    (f: number) => {
      const c = Math.max(0, Math.min(n - 1, f));
      setFrame(c);
      const v = videoRef.current;
      if (v && pts.length) v.currentTime = pts[c] + 0.001;
    },
    [n, pts],
  );

  const pause = useCallback(() => {
    stopReverse();
    const v = videoRef.current;
    if (v && !v.paused) {
      v.pause();
      setFrame(nearestFrame(pts, v.currentTime));
    }
    setPlaying(false);
  }, [pts]);

  const play = useCallback(
    (r: number) => {
      stopReverse();
      const v = videoRef.current;
      if (!v) return;
      v.currentTime = pts[frame] + 0.001;
      v.playbackRate = r;
      setRate(r);
      setPlaying(true);
      void v.play();
      const tick = (_now: number, meta: { mediaTime: number }) => {
        if (v.paused) return;
        setFrame(nearestFrame(pts, meta.mediaTime));
        v.requestVideoFrameCallback(tick);
      };
      if ("requestVideoFrameCallback" in v) v.requestVideoFrameCallback(tick);
    },
    [frame, pts],
  );

  const playReverse = useCallback(
    (r: number) => {
      pause();
      setRate(r);
      reverseTimer.current = window.setInterval(() => {
        setFrame((f) => {
          if (f <= 0) {
            stopReverse();
            return 0;
          }
          return f - 1;
        });
      }, 1000 / (fps * r));
    },
    [pause, fps],
  );

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    const ended = () => {
      setPlaying(false);
      setFrame(n - 1);
    };
    v.addEventListener("ended", ended);
    return () => v.removeEventListener("ended", ended);
  }, [n, video]);

  // ---- Eventos ------------------------------------------------------------------------
  // Alterações em fila: o servidor recebe na ordem das teclas e a tela nunca volta para
  // uma resposta mais antiga.
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const patch = useCallback(
    (body: Parameters<typeof api.patchEvents>[1]) => {
      const run = queue.current.then(async () => {
        try {
          const st = await api.patchEvents(videoId, body);
          apply(st);
          setError(null);
          return st;
        } catch (e) {
          setError(String((e as Error).message));
          return null;
        }
      });
      queue.current = run;
      return run;
    },
    [videoId, apply],
  );

  // Criação em andamento: um clique no quadro logo após a tecla espera por ela.
  const pendingCreate = useRef<Promise<string | null> | null>(null);

  const createEvent = useCallback(
    async (type: EventType) => {
      pause();
      const job = patch({
        create: [{ type, frame, mark_m: type === "mark_pass" ? markM : null }],
      }).then((st) => st?.created_ids[0] ?? null);
      pendingCreate.current = job;
      const id = await job;
      if (pendingCreate.current === job) pendingCreate.current = null;
      if (id) {
        setSelectedId(id);
        setCycleType(type);
      }
    },
    [frame, markM, patch, pause, setSelectedId],
  );

  const jumpType = (dir: 1 | -1) => {
    const list = events.filter((e) => e.type === cycleType).sort((a, b) => a.t - b.t);
    const t = pts[frame] ?? 0;
    const target =
      dir > 0 ? list.find((e) => e.t > t + 1e-6) : [...list].reverse().find((e) => e.t < t - 1e-6);
    if (target) {
      setSelectedId(target.id);
      seek(target.frame);
    }
  };

  const nextAlert = () => {
    const t = pts[frame] ?? 0;
    const withT = alerts.filter((a) => a.t_from != null).sort((a, b) => a.t_from! - b.t_from!);
    const a = withT.find((x) => x.t_from! > t + 1e-6) ?? withT[0];
    if (a) seek(nearestFrame(pts, a.t_from!));
  };

  // ---- Calibração -------------------------------------------------------------------
  const nearestResult = useMemo(() => {
    const ok = results.filter((r) => r.accepted);
    if (!ok.length) return null;
    return ok.reduce((b, r) => (Math.abs(r.frame - frame) < Math.abs(b.frame - frame) ? r : b));
  }, [results, frame]);

  const saveCalibration = async () => {
    if (!pool) return;
    setCalBusy(true);
    setCalMsg(null);
    try {
      const out = await api.saveCalibration(videoId, pool, anchors);
      setResults(out.calibration.results);
      setGrids(out.grids);
      apply(out);
      setCalDirty(false);
      gridCache.current.clear();
      onVideo(out.video);
    } catch (e) {
      setCalMsg(String((e as Error).message));
    } finally {
      setCalBusy(false);
    }
  };

  const copyCalibration = async (from: string) => {
    try {
      const out = await api.copyCalibration(videoId, from);
      setPool(out.calibration.pool);
      setAnchors(out.calibration.anchors);
      setResults(out.calibration.results);
      setGrids(out.grids);
      apply(out);
      setCalDirty(false);
      gridCache.current.clear();
      onVideo(out.video);
    } catch (e) {
      setCalMsg(String((e as Error).message));
    }
  };

  function frameClick(x: number, y: number) {
    if (mode === "calibration" && pool) {
      const anchor = anchors.find((a) => a.frame === frame);
      if (!anchor) {
        setCalMsg("Crie uma âncora neste quadro antes de clicar os pontos.");
        return;
      }
      const point = { image_xy: [x, y] as [number, number], pool_xy: [pick.x, pick.rope * pool.lane_width_m] as [number, number] };
      setAnchors(anchors.map((a) => (a.frame === frame ? { ...a, points: [...a.points, point] } : a)));
      setPick(nextPick(pool, pick));
      setCalDirty(true);
      setCalMsg(null);
      return;
    }
    void (async () => {
      const id = pendingCreate.current ? await pendingCreate.current : selectedRef.current;
      if (id) await patch({ update: [{ id, image_xy: [x, y] }] });
    })();
  }

  // Grade do quadro atual (câmera em movimento: cada quadro tem a sua)
  const hasCalibration = results.some((r) => r.accepted);
  useEffect(() => {
    if (playing || !showGrid || !hasCalibration || calDirty) return;
    const cached = gridCache.current.get(frame);
    if (cached) {
      setFrameGrid(cached);
      return;
    }
    const h = window.setTimeout(() => {
      api
        .grid(videoId, frame)
        .then((g) => {
          gridCache.current.set(frame, g.lines);
          setFrameGrid(g.lines);
        })
        .catch(() => undefined);
    }, 120);
    return () => window.clearTimeout(h);
  }, [frame, playing, showGrid, hasCalibration, calDirty, videoId]);

  // ---- Teclado ------------------------------------------------------------------------
  const keyRef = useRef<(e: KeyboardEvent) => void>(() => undefined);
  keyRef.current = (e: KeyboardEvent) => {
    const tag = (e.target as HTMLElement).tagName;
    if (["INPUT", "SELECT", "TEXTAREA"].includes(tag) || e.ctrlKey || e.metaKey || e.altKey) return;
    const k = e.key.toLowerCase();
    const step = e.shiftKey ? 10 : 1;
    if (e.key === "ArrowRight") {
      pause();
      seek(frame + step);
    } else if (e.key === "ArrowLeft") {
      pause();
      seek(frame - step);
    } else if (k === "k" || e.key === " ") {
      if (playing || reverseTimer.current) pause();
      else play(rate);
    } else if (k === "l") {
      const next = playing ? RATES[Math.min(RATES.length - 1, RATES.indexOf(rate) + 1)] : 1;
      play(next);
    } else if (k === "j") {
      const next = reverseTimer.current ? RATES[Math.min(1, RATES.indexOf(rate) + 1)] : 0.25;
      playReverse(next);
    } else if (e.key === "Delete" || e.key === "Backspace") {
      if (selected) {
        void patch({ delete: [selected.id] });
        setSelectedId(null);
      }
    } else if (e.key === "[") jumpType(-1);
    else if (e.key === "]") jumpType(1);
    else if (k === "n") nextAlert();
    else if (k === "g") setShowGrid((s) => !s);
    else if (k === "v") setShowOverlay((s) => !s);
    else if (e.key === "." && selected) void patch({ update: [{ id: selected.id, frame }] });
    else if (e.key === "Escape") setSelectedId(null);
    else if (mode === "review" && KEY_TO_TYPE[k]) void createEvent(KEY_TO_TYPE[k]);
    else return;
    e.preventDefault();
  };
  useEffect(() => {
    const h = (e: KeyboardEvent) => keyRef.current(e);
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, []);

  // ---- Render -------------------------------------------------------------------------
  if (error && !video) return <div className="page"><p className="error">{error}</p></div>;
  if (!video || !video.meta || !race || !pool || !pts.length) return <div className="page muted">Carregando…</div>;

  const { proxy_width: W, proxy_height: H } = video.meta;
  const here = events.filter((e) => e.frame === frame && e.image_xy);
  const grid = mode === "calibration" ? grids[String(frame)] ?? (nearestResult ? grids[String(nearestResult.frame)] : undefined)
    : showGrid && nearestResult ? frameGrid ?? grids[String(nearestResult.frame)] : undefined;
  const anchorHere = anchors.find((a) => a.frame === frame);
  const resultHere = results.find((r) => r.frame === frame);

  return (
    <div className="review">
      <div className="review-head">
        <div>
          <h1>{video.title}</h1>
          <p className="muted">
            {video.athlete ? `${video.athlete} · ` : ""}
            {STROKE_LABEL[race.stroke]} · {race.distance} m · piscina {race.pool_length} m
            {race.lane ? ` · raia ${race.lane}` : ""} · {video.meta.n_frames} quadros a{" "}
            {video.meta.fps_measured.toFixed(1)} fps{video.meta.variable_frame_rate ? " (taxa variável)" : ""}
            {" · "}
            <button className="link" onClick={() => setEditRace((s) => !s)}>
              {editRace ? "fechar dados da prova" : "editar dados da prova"}
            </button>
          </p>
          {video.warnings.map((w) => (
            <p key={w} className="warn small">{w}</p>
          ))}
        </div>
        <div className="tabs">
          <button className={mode === "review" ? "active" : ""} onClick={() => setMode("review")}>
            Revisão
          </button>
          <button className={mode === "calibration" ? "active" : ""} onClick={() => setMode("calibration")}>
            Calibração{results.some((r) => r.accepted) ? " ✓" : ""}
          </button>
        </div>
      </div>

      <div className={`analysis-bar ${video.analysis_status}`}>
        <div>
          <b>Análise automática:</b>{" "}
          {{
            idle: "ainda não rodou",
            queued: "na fila…",
            running: "analisando o vídeo…",
            done: "concluída",
            failed: "não concluída",
          }[video.analysis_status]}
          {!video.calibration_ok && " · calibre a piscina (aba Calibração) para começar"}
          {video.calibration_ok && !race.lane && " · informe a raia em “editar dados da prova”"}
          {video.analysis_notes.length > 0 && (
            <ul>
              {video.analysis_notes.map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ul>
          )}
        </div>
        <button
          className="btn small"
          disabled={analysisActive || !video.calibration_ok || !race.lane}
          onClick={runAnalysis}
        >
          {analysisActive ? "Analisando…" : video.analysis_status === "idle" ? "Analisar" : "Analisar de novo"}
        </button>
      </div>

      {editRace && (
        <div className="card">
          <RaceFields
            race={race}
            onChange={async (r) => {
              try {
                onVideo(await api.updateRace(videoId, r));
                apply(await api.events(videoId));
              } catch (e) {
                setError(String((e as Error).message));
              }
            }}
          />
        </div>
      )}

      <div className="review-body">
        <div className="stage">
          <div className="present-box" ref={frameBox} style={{ ["--ar" as string]: `${W / H}` }}>
          <FrameView
            videoId={videoId}
            width={W}
            height={H}
            frame={frame}
            nFrames={n}
            playing={playing}
            videoRef={videoRef}
            onClick={frameClick}
            cursor={mode === "calibration" || selected ? "crosshair" : "default"}
            hud={
              mode === "review" && showOverlay && overlay ? (
                <LiveOverlay tl={overlay} t={pts[frame] ?? 0} />
              ) : null
            }
          >
            {!present && grid?.map((ln, i) => (
              <polyline
                key={i}
                points={ln.points.map((p) => p.join(",")).join(" ")}
                className={ln.kind === "rope" ? "grid rope" : ln.value === 15 || ln.value === (pool.length_m - 15) ? "grid mark15" : "grid"}
              />
            ))}
            {mode === "calibration" &&
              anchorHere?.points.map((p, i) => (
                <g key={i}>
                  <circle cx={p.image_xy[0]} cy={p.image_xy[1]} r={W / 160}
                    className={resultHere && resultHere.inliers[i] === false ? "cal-pt bad" : "cal-pt"} />
                  <text x={p.image_xy[0] + W / 120} y={p.image_xy[1] - W / 160} className="cal-label">
                    {i + 1}
                  </text>
                </g>
              ))}
            {mode === "review" && !present &&
              here.map((e) => (
                <g key={e.id}>
                  <circle cx={e.image_xy![0]} cy={e.image_xy![1]} r={W / 110} fill="none"
                    stroke={EVENT_COLOR[e.type]} strokeWidth={e.id === selectedId ? 4 : 2.5} />
                  <text x={e.image_xy![0] + W / 90} y={e.image_xy![1]} className="ev-label" fill={EVENT_COLOR[e.type]}>
                    {EVENT_LABEL[e.type]}
                    {e.x_m != null ? ` · ${e.x_m.toFixed(1).replace(".", ",")} m` : ""}
                  </text>
                </g>
              ))}
            {mode === "review" && !present && !(showOverlay && overlay) && traj && frame < traj.frame.length && (
              <g className="swimmer" style={{ opacity: 0.4 + 0.6 * traj.confidence[frame] }}>
                <circle cx={traj.head_img_x[frame]} cy={traj.head_img_y[frame]} r={W / 70} />
                <line x1={traj.head_img_x[frame] - W / 45} x2={traj.head_img_x[frame] + W / 45}
                  y1={traj.head_img_y[frame]} y2={traj.head_img_y[frame]} />
                <text x={traj.head_img_x[frame] + W / 60} y={traj.head_img_y[frame] - W / 60}
                  className="ev-label swimmer-label">
                  {traj.head_x[frame].toFixed(1).replace(".", ",")} m
                </text>
              </g>
            )}
          </FrameView>
          </div>

          <div className="transport">
            <button className="btn small" onClick={() => { pause(); seek(frame - 1); }} title="Quadro anterior (←)">◀︎ 1</button>
            {playing ? (
              <button className="btn small" onClick={pause} title="Pausar (K)">Pausar</button>
            ) : (
              <button className="btn small" onClick={() => play(rate)} title="Reproduzir (K)">Reproduzir</button>
            )}
            <button className="btn small" onClick={() => { pause(); seek(frame + 1); }} title="Próximo quadro (→)">1 ▶︎</button>
            <select value={rate} onChange={(e) => setRate(Number(e.target.value))} title="Velocidade">
              {RATES.map((r) => (
                <option key={r} value={r}>{r}×</option>
              ))}
            </select>
            <span className="clock">
              Quadro <b>{frame}</b> / {n - 1} · {fmtTime(pts[frame])}
              {(() => {
                const st = events.find((e) => e.type === "start_signal");
                return st ? ` · prova ${fmtTime(pts[frame] - st.t)}` : "";
              })()}
            </span>
            <label className="zoom">
              Zoom
              <select value={zoom} onChange={(e) => setZoom(Number(e.target.value))}>
                {[1, 2, 4, 8, 16].map((z) => (
                  <option key={z} value={z}>{z}×</option>
                ))}
              </select>
            </label>
            <label className="zoom">
              <input type="checkbox" checked={showGrid} onChange={(e) => setShowGrid(e.target.checked)} /> Grade (G)
            </label>
            {mode === "review" && (
              <>
                <label className="zoom">
                  <input
                    type="checkbox"
                    checked={showOverlay}
                    onChange={(e) => setShowOverlay(e.target.checked)}
                  />{" "}
                  Sobreposição (V)
                </label>
                <button className="btn small fx-btn" onClick={togglePresent} title="Tela cheia com a sobreposição, sem marcações de edição">
                  {present ? "Sair da apresentação" : "Modo apresentação"}
                </button>
              </>
            )}
          </div>

          <Timeline
            pts={pts}
            frame={frame}
            events={events}
            alerts={alerts}
            waveform={waveform}
            selectedId={selectedId}
            zoom={zoom}
            onSeek={(f) => { pause(); seek(f); }}
            onSelect={(id) => {
              const ev = events.find((e) => e.id === id);
              setSelectedId(id);
              if (ev) { setCycleType(ev.type); pause(); seek(ev.frame); }
            }}
          />
          {error && <p className="error">{error}</p>}
        </div>

        <aside className="side">
          {mode === "review" ? (
            <>
              <section className="card">
                <h3>Marcar evento no quadro atual</h3>
                <div className="keys">
                  {(Object.keys(EVENT_LABEL) as EventType[])
                    .filter((t) => race.stroke === "breaststroke" || t !== "wall_hands")
                    .map((t) => (
                      <button key={t} className="key" onClick={() => createEvent(t)}>
                        <kbd style={{ borderColor: EVENT_COLOR[t] }}>{EVENT_KEY[t]}</kbd> {EVENT_LABEL[t]}
                      </button>
                    ))}
                </div>
                <label className="inline small">
                  Marca para “P”:
                  <select value={markM} onChange={(e) => setMarkM(Number(e.target.value))}>
                    {[5, 10, 15, 20].map((m) => (
                      <option key={m} value={m}>{m} m da parede de impulsão</option>
                    ))}
                  </select>
                </label>
                <p className="muted small">
                  ← → quadro · Shift ±10 · K/espaço pausa · L avança · J volta · [ ] anterior/próximo
                  do tipo · “.” move o selecionado para cá · Del apaga · N próximo alerta
                </p>
              </section>

              {selected && (
                <section className="card selected">
                  <h3 style={{ color: EVENT_COLOR[selected.type] }}>{EVENT_LABEL[selected.type]}</h3>
                  <p className="muted small">
                    {selected.source === "auto"
                      ? `Automático · confiança ${Math.round(selected.confidence * 100)}%`
                      : "Marcado ou corrigido por você"}
                  </p>
                  <p>
                    Quadro {selected.frame} · {fmtTime(selected.t)}
                    {selected.x_m != null && ` · ${selected.x_m.toFixed(2).replace(".", ",")} m da parede de saída`}
                  </p>
                  {!selected.image_xy && (
                    <p className="hint">
                      {nearestResult
                        ? "Clique na cabeça do nadador no quadro para dar a posição."
                        : "Sem calibração: a posição na piscina só é calculada depois de calibrar."}
                    </p>
                  )}
                  <div className="row-actions">
                    <button className="btn small" onClick={() => seek(selected.frame)}>Ir ao quadro</button>
                    <button className="btn small" onClick={() => patch({ update: [{ id: selected.id, frame }] })}>
                      Mover para o quadro {frame}
                    </button>
                    {selected.image_xy && (
                      <button className="btn small" onClick={() => patch({ update: [{ id: selected.id, clear_image_xy: true }] })}>
                        Tirar posição
                      </button>
                    )}
                    <button className="btn small danger" onClick={() => { void patch({ delete: [selected.id] }); setSelectedId(null); }}>
                      Apagar
                    </button>
                  </div>
                </section>
              )}

              {alerts.length > 0 && (
                <section className="card">
                  <h3>Alertas ({alerts.length})</h3>
                  <ul className="alerts">
                    {alerts.map((a, i) => (
                      <li key={i}>
                        {a.t_from != null ? (
                          <button className="link" onClick={() => { pause(); seek(nearestFrame(pts, a.t_from!)); }}>
                            {fmtTime(a.t_from)}
                          </button>
                        ) : null}{" "}
                        {a.message}
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              <section className="card">
                <MetricsPanel metrics={metrics} race={race} />
              </section>
            </>
          ) : (
            <section className="card">
              <CalibrationPanel
                videoId={videoId}
                frame={frame}
                pool={pool}
                anchors={anchors}
                results={results}
                pick={pick}
                dirty={calDirty}
                busy={calBusy}
                message={calMsg}
                onPool={(p) => { setPool(p); setCalDirty(true); }}
                onPick={setPick}
                onAnchors={(a) => { setAnchors(a); setCalDirty(true); }}
                onSave={saveCalibration}
                onSeek={(f) => { pause(); seek(f); }}
                onCopyFrom={copyCalibration}
              />
            </section>
          )}
        </aside>
      </div>
    </div>
  );
}
