import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { fmtTime } from "../labels";
import type { TechNote, TechPhase, TechState } from "../types";

type Props = {
  videoId: string;
  width: number;
  height: number;
  frame: number;
  t: number;
  lane: number | null;
  pts: number[];
  eventsKey: string; // muda quando os eventos mudam: recarrega as sugestões
  onSeek: (frame: number) => void;
  requestMark: (cb: (x: number, y: number) => void) => void;
  onError: (m: string) => void;
};

let seq = 0;
const newId = () => `n${Date.now().toString(36)}${(seq++).toString(36)}`;

/**
 * Técnica, quadro a quadro: um quadro-chave por fase da prova, com os pontos técnicos daquela
 * fase em botões. A IA (se configurada) sugere; o treinador confirma.
 */
export default function TechniquePanel(p: Props) {
  const [st, setSt] = useState<TechState | null>(null);
  const [notes, setNotes] = useState<TechNote[]>([]);
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);
  const saveTimer = useRef<number | null>(null);
  const loaded = useRef(false);
  // espelho síncrono: pedidos à IA em sequência sempre partem da lista mais nova
  const notesRef = useRef<TechNote[]>([]);

  useEffect(() => {
    api
      .technique(p.videoId)
      .then((s) => {
        setSt(s);
        if (!loaded.current) {
          setNotes(s.notes);
          notesRef.current = s.notes;
          loaded.current = true;
        }
      })
      .catch((e) => p.onError(String((e as Error).message)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p.videoId, p.eventsKey]);

  const persist = useCallback(
    (next: TechNote[]) => {
      notesRef.current = next;
      setNotes(next);
      if (saveTimer.current) window.clearTimeout(saveTimer.current);
      saveTimer.current = window.setTimeout(async () => {
        setSaving(true);
        try {
          await api.saveTechnique(p.videoId, next);
        } catch (e) {
          p.onError(String((e as Error).message));
        } finally {
          setSaving(false);
        }
      }, 500);
    },
    [p],
  );

  const phases = useMemo(() => new Map((st?.catalog ?? []).map((ph) => [ph.key, ph])), [st]);
  if (!st) return null;

  const update = (id: string, patch: Partial<TechNote>) =>
    persist(notesRef.current.map((n) => (n.id === id ? { ...n, ...patch } : n)));

  const frameAt = (t: number) => {
    let best = 0;
    for (let i = 0; i < p.pts.length; i++) if (Math.abs(p.pts[i] - t) < Math.abs(p.pts[best] - t)) best = i;
    return best;
  };

  const missing = st.suggestions.filter(
    (s) => !notes.some((n) => n.phase === s.phase && n.lane === s.lane),
  );
  const addSuggested = () => {
    const add: TechNote[] = missing.map((s) => {
      const frame = s.dt ? frameAt(s.t + s.dt) : s.frame;
      return {
        id: newId(),
        frame,
        t: p.pts[frame] ?? s.t,
        lane: s.lane,
        phase: s.phase,
        items: [],
        text: "",
        mark: null,
        source: "coach",
        confirmed: true,
      };
    });
    persist([...notes, ...add].sort((a, b) => (a.lane ?? 0) - (b.lane ?? 0) || a.t - b.t));
  };
  const addCurrent = () => {
    const n: TechNote = {
      id: newId(),
      frame: p.frame,
      t: p.t,
      lane: p.lane,
      phase: null,
      items: [],
      text: "",
      mark: null,
      source: "coach",
      confirmed: true,
    };
    persist([...notes, n].sort((a, b) => (a.lane ?? 0) - (b.lane ?? 0) || a.t - b.t));
  };

  const askAI = async (n: TechNote) => {
    if (!n.phase) return;
    setBusy((b) => ({ ...b, [n.id]: true }));
    try {
      const r = await api.techAI(p.videoId, { frame: n.frame, phase: n.phase, lane: n.lane, mark: n.mark });
      persist(
        notesRef.current.map((x) =>
          x.id !== n.id
            ? x
            : {
                ...x,
                items: r.items,
                text: r.text && !x.text ? r.text : x.text,
                source: "ai" as const,
                confirmed: false,
              },
        ),
      );
      if (!r.visible) p.onError("A IA não conseguiu ver bem esse quadro: escolha outro ou marque à mão.");
    } catch (e) {
      p.onError(String((e as Error).message));
    } finally {
      setBusy((b) => ({ ...b, [n.id]: false }));
    }
  };
  const askAll = async () => {
    for (const n of notesRef.current.filter((x) => x.phase && x.items.length === 0)) await askAI(n);
  };

  const open = notes.filter((n) => !n.confirmed).length;

  return (
    <section className="card technique" data-testid="technique">
      <div className="tech-head">
        <h3>Técnica, quadro a quadro</h3>
        <span className="muted small">
          {saving ? "salvando…" : notes.length ? `${notes.length} quadros` : ""}
          {open ? ` · ${open} sugestão(ões) da IA para confirmar` : ""}
        </span>
      </div>
      <p className="muted small">
        Um quadro de cada fase da prova. Toque nos pontos que você vê: cada um já traz a frase para
        o atleta e um exercício, que entram na devolutiva.
      </p>
      <div className="row-actions">
        {missing.length > 0 && (
          <button className="btn small primary" onClick={addSuggested} data-testid="tech-suggest">
            Sugerir {missing.length} quadros a partir das marcações
          </button>
        )}
        <button className="btn small" onClick={addCurrent} data-testid="tech-add">
          + Quadro atual ({fmtTime(p.t)})
        </button>
        {st.ai_enabled && notes.some((n) => n.phase && n.items.length === 0) && (
          <button className="btn small fx-btn" onClick={() => void askAll()}>
            Sugerir pontos com IA
          </button>
        )}
      </div>
      {!st.ai_enabled && (
        <p className="muted small">
          Sugestão por IA desligada: defina ANTHROPIC_API_KEY no .env para a IA pré-marcar os pontos.
        </p>
      )}

      <div className="tech-grid">
        {notes.map((n) => (
          <NoteCard
            key={n.id}
            n={n}
            ph={n.phase ? phases.get(n.phase) : undefined}
            catalog={st.catalog}
            videoId={p.videoId}
            width={p.width}
            height={p.height}
            busy={!!busy[n.id]}
            ai={st.ai_enabled}
            isHere={n.frame === p.frame}
            onSeek={() => p.onSeek(n.frame)}
            onChange={(patch) => update(n.id, patch)}
            onDelete={() => persist(notes.filter((x) => x.id !== n.id))}
            onMark={() => p.requestMark((x, y) => update(n.id, { mark: [x, y] }))}
            onMoveHere={() => update(n.id, { frame: p.frame, t: p.t, mark: null })}
            onAI={() => void askAI(n)}
          />
        ))}
      </div>
    </section>
  );
}

function NoteCard(props: {
  n: TechNote;
  ph?: TechPhase;
  catalog: TechPhase[];
  videoId: string;
  width: number;
  height: number;
  busy: boolean;
  ai: boolean;
  isHere: boolean;
  onSeek: () => void;
  onChange: (p: Partial<TechNote>) => void;
  onDelete: () => void;
  onMark: () => void;
  onMoveHere: () => void;
  onAI: () => void;
}) {
  const { n, ph } = props;
  const toggle = (k: string) =>
    props.onChange({
      items: n.items.includes(k) ? n.items.filter((x) => x !== k) : [...n.items, k],
      confirmed: true,
      source: "coach",
    });
  return (
    <div className={`tech-card ${n.confirmed ? "" : "ai-pending"}`} data-testid="tech-card">
      <button
        className="tech-shot"
        style={{ aspectRatio: `${props.width} / ${props.height}` }}
        onClick={props.onSeek}
        title="Ir para este quadro"
      >
        <img src={`/api/videos/${props.videoId}/frames/${n.frame}.jpg`} alt="" loading="lazy" />
        {/* miniatura do quadro inteiro; o cliente vê o recorte ampliado em volta do círculo */}
        {n.mark && (
          <span
            className="tech-ring"
            style={{ left: `${(100 * n.mark[0]) / props.width}%`, top: `${(100 * n.mark[1]) / props.height}%` }}
          />
        )}
      </button>
      <div className="tech-body">
        <div className="tech-title">
          {n.lane != null && <span className="lane-dot">{n.lane}</span>}
          <select
            value={n.phase ?? ""}
            onChange={(e) => props.onChange({ phase: e.target.value || null, items: [] })}
            aria-label="Fase"
          >
            <option value="">Fase…</option>
            {props.catalog.map((c) => (
              <option key={c.key} value={c.key}>
                {c.label}
              </option>
            ))}
          </select>
          <span className="muted small">{fmtTime(n.t)}</span>
        </div>
        {ph && <p className="muted small hint">{ph.hint}</p>}
        {!n.confirmed && (
          <div className="ai-note small">
            Sugestão da IA. Confira no quadro e confirme.
            <button className="btn small primary" onClick={() => props.onChange({ confirmed: true })}>
              Confirmar
            </button>
          </div>
        )}
        {ph && (
          <div className="tech-items">
            {ph.items.map((it) => (
              <button
                key={it.key}
                className={`titem ${it.good ? "good" : "fix"} ${n.items.includes(it.key) ? "on" : ""}`}
                onClick={() => toggle(it.key)}
                title={it.text + (it.drill ? `\nExercício: ${it.drill}` : "")}
              >
                {it.label}
              </button>
            ))}
          </div>
        )}
        <textarea
          rows={2}
          placeholder="Observação própria (opcional)"
          value={n.text}
          maxLength={600}
          onChange={(e) => props.onChange({ text: e.target.value })}
        />
        <div className="tech-acts">
          <button className="btn small ghost" onClick={props.onMark} title="Toque no vídeo para marcar o ponto">
            {n.mark ? "Mudar círculo" : "Circular no quadro"}
          </button>
          {!props.isHere && (
            <button className="btn small ghost" onClick={props.onMoveHere} title="Usar o quadro que está no vídeo">
              Usar quadro atual
            </button>
          )}
          {props.ai && ph && (
            <button className="btn small ghost" disabled={props.busy} onClick={props.onAI}>
              {props.busy ? "IA olhando…" : "IA"}
            </button>
          )}
          <button className="btn small ghost danger" onClick={props.onDelete} aria-label="Remover quadro">
            ✕
          </button>
        </div>
      </div>
    </div>
  );
}
