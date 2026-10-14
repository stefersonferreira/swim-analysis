import { useEffect, useState } from "react";
import { api } from "../api";
import type { Feedback, Video } from "../types";

const LISTS: { key: "strengths" | "improve" | "drills"; label: string; hint: string }[] = [
  { key: "strengths", label: "Pontos fortes", hint: "Um por linha" },
  { key: "improve", label: "O que melhorar", hint: "Um por linha" },
  { key: "drills", label: "Exercícios sugeridos", hint: "Um por linha" },
];

const empty: Feedback = { summary: "", strengths: [], improve: [], drills: [] };

function toText(fb: Feedback | null) {
  const f = fb ?? empty;
  return {
    summary: f.summary,
    strengths: f.strengths.join("\n"),
    improve: f.improve.join("\n"),
    drills: f.drills.join("\n"),
  };
}

function lines(s: string): string[] {
  return s.split("\n").map((x) => x.replace(/^[-•]\s*/, "").trim()).filter(Boolean);
}

/** Número do WhatsApp no formato do wa.me (Brasil quando vier sem código do país). */
export function waNumber(phone: string | null): string | null {
  const d = (phone ?? "").replace(/\D/g, "");
  if (d.length < 10) return null;
  return d.length <= 11 ? `55${d}` : d;
}

/** Devolutiva do treinador e entrega do pedido ao cliente. */
export default function DeliveryPanel(props: {
  video: Video;
  onVideo: (v: Video) => void;
  onError: (m: string) => void;
}) {
  const { video } = props;
  const o = video.order;
  const [text, setText] = useState(toText(o.feedback));
  const [busy, setBusy] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  useEffect(() => setText(toText(o.feedback)), [video.id, o.feedback]);

  const fb: Feedback = {
    summary: text.summary.trim(),
    strengths: lines(text.strengths),
    improve: lines(text.improve),
    drills: lines(text.drills),
  };
  const saved = JSON.stringify(toText(o.feedback)) === JSON.stringify(toText(fb));
  const hasFb = !!(fb.summary || fb.strengths.length || fb.improve.length || fb.drills.length);
  const link = `${window.location.origin}${o.share_path}`;
  const wa = waNumber(o.customer_phone);
  const first = (o.customer_name ?? video.athlete ?? "").split(" ")[0];
  const msg = `Olá${first ? `, ${first}` : ""}! Sua análise de nado Fluxi Swim está pronta: ${link}`;

  const run = async (what: string, f: () => Promise<void>) => {
    setBusy(what);
    try {
      await f();
    } catch (e) {
      props.onError(String((e as Error).message));
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="card delivery" data-testid="delivery">
      <h3>Devolutiva e entrega</h3>
      {o.origin === "client" && (
        <div className="order-info small">
          <b>{o.customer_name}</b>
          {o.customer_phone && ` · ${o.customer_phone}`}
          {o.customer_email && ` · ${o.customer_email}`}
          {o.customer_notes && <div className="quote">“{o.customer_notes}”</div>}
          {o.due_at && o.status !== "delivered" && (
            <div className="muted">Prazo: {new Date(o.due_at).toLocaleString("pt-BR")}</div>
          )}
        </div>
      )}

      <button
        className="btn small"
        disabled={!!busy}
        onClick={() =>
          run("draft", async () => {
            if (hasFb && !window.confirm("Substituir o texto atual pelo rascunho gerado dos números?")) return;
            setText(toText(await api.draftFeedback(video.id)));
          })
        }
        data-testid="draft"
      >
        {busy === "draft" ? "Gerando…" : "Gerar rascunho a partir dos números"}
      </button>
      <p className="muted small">O rascunho sai só do que foi medido. Revise e complete com o seu olhar.</p>

      <label className="block small">
        Resumo
        <textarea
          rows={3}
          value={text.summary}
          maxLength={2000}
          onChange={(e) => setText({ ...text, summary: e.target.value })}
          placeholder="Uma ou duas frases com o principal da análise"
        />
      </label>
      {LISTS.map((l) => (
        <label key={l.key} className="block small">
          {l.label} <span className="muted">({l.hint.toLowerCase()})</span>
          <textarea
            rows={3}
            value={text[l.key]}
            onChange={(e) => setText({ ...text, [l.key]: e.target.value })}
          />
        </label>
      ))}
      <div className="row-actions">
        <button
          className="btn small primary"
          disabled={saved || !!busy}
          onClick={() => run("save", async () => props.onVideo(await api.saveFeedback(video.id, fb)))}
          data-testid="save-feedback"
        >
          {busy === "save" ? "Salvando…" : saved ? "Salvo" : "Salvar devolutiva"}
        </button>
      </div>

      <hr />
      {o.status !== "delivered" ? (
        <>
          {video.export_status !== "done" && (
            <p className="warn small">Gere o vídeo antes de entregar, para o cliente poder assistir.</p>
          )}
          <button
            className="btn fx-btn"
            disabled={!o.feedback || !saved || !!busy}
            title={!o.feedback ? "Salve a devolutiva primeiro" : ""}
            onClick={() => run("deliver", async () => props.onVideo(await api.deliver(video.id)))}
            data-testid="deliver"
          >
            {busy === "deliver" ? "Entregando…" : "Entregar ao cliente"}
          </button>
        </>
      ) : (
        <div className="delivered">
          <b>Entregue ✓</b>
          {o.delivered_at && <span className="muted small"> {new Date(o.delivered_at).toLocaleString("pt-BR")}</span>}
          {!saved && <p className="warn small">Há mudanças na devolutiva: salve para o cliente ver.</p>}
          <div className="row-actions">
            {wa && (
              <a className="btn small primary" href={`https://wa.me/${wa}?text=${encodeURIComponent(msg)}`} target="_blank" rel="noreferrer">
                Enviar no WhatsApp
              </a>
            )}
            {o.customer_email && (
              <a className="btn small" href={`mailto:${o.customer_email}?subject=${encodeURIComponent("Sua análise Fluxi Swim")}&body=${encodeURIComponent(msg)}`}>
                Enviar por e-mail
              </a>
            )}
            <button
              className="btn small"
              onClick={() => {
                void navigator.clipboard?.writeText(link);
                setCopied(true);
              }}
            >
              {copied ? "Link copiado" : "Copiar link"}
            </button>
            <a className="btn small" href={o.share_path} target="_blank" rel="noreferrer">
              Ver como o cliente
            </a>
          </div>
          <button
            className="link small"
            onClick={() => run("reopen", async () => props.onVideo(await api.updateOrder(video.id, { status: "reviewing" })))}
          >
            Desfazer entrega
          </button>
        </div>
      )}
    </section>
  );
}
