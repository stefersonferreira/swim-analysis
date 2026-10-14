import { useEffect, useState } from "react";
import { api } from "../../api";
import type { PublicOrder } from "../../types";
import "./client.css";

const STEPS: { key: string; label: string }[] = [
  { key: "received", label: "Vídeo recebido" },
  { key: "reviewing", label: "Em análise" },
  { key: "delivered", label: "Entregue" },
];

function stepIndex(o: PublicOrder): number {
  if (o.delivered) return 2;
  if (o.status === "reviewing" || o.video_status === "ready") return 1;
  return 0;
}

function fmtDate(s: string | null): string {
  if (!s) return "";
  return new Date(s).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

/** Link do cliente: acompanha o pedido e, quando entregue, mostra tudo. */
export default function Delivery({ token }: { token: string }) {
  const [o, setO] = useState<PublicOrder | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fresh = new URLSearchParams(window.location.search).has("novo");
  const link = `${window.location.origin}/r/${token}`;
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let alive = true;
    const load = () =>
      api
        .publicOrder(token)
        .then((x) => alive && setO(x))
        .catch((e) => alive && setError(String((e as Error).message)));
    load();
    const id = window.setInterval(load, 30000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, [token]);

  if (error) return <div className="client"><p className="client-error">{error}</p></div>;
  if (!o) return <div className="client muted">Carregando…</div>;
  const k = stepIndex(o);
  const share = `https://wa.me/?text=${encodeURIComponent(`Minha análise de nado Fluxi Swim: ${link}`)}`;

  return (
    <div className="client">
      <header className="client-head">
        <div className="brand-word">Fluxi Swim</div>
        <h1>{o.title}</h1>
        {o.first_name && !o.delivered && <p className="lead">Olá, {o.first_name}!</p>}
      </header>

      {fresh && !o.delivered && (
        <section className="client-card ok-card">
          <b>Vídeo enviado ✓</b>
          <p>
            Guarde este link: é por ele que você recebe a análise. Entrega até{" "}
            <b>{fmtDate(o.due_at)}</b>.
          </p>
          <div className="copy-row">
            <input readOnly value={link} onFocus={(e) => e.target.select()} />
            <button
              type="button"
              onClick={() => {
                void navigator.clipboard?.writeText(link);
                setCopied(true);
              }}
            >
              {copied ? "Copiado" : "Copiar"}
            </button>
          </div>
        </section>
      )}

      {!o.delivered && (
        <section className="client-card">
          <ol className="progress-steps">
            {STEPS.map((s, i) => (
              <li key={s.key} className={i < k ? "done" : i === k ? "now" : ""}>
                <span />
                {s.label}
              </li>
            ))}
          </ol>
          {o.error ? (
            <p className="client-error">Houve um problema com o vídeo: {o.error}</p>
          ) : (
            <p className="muted">
              Previsão de entrega: <b>{fmtDate(o.due_at)}</b>. Esta página se atualiza sozinha.
            </p>
          )}
        </section>
      )}

      {o.delivered && (
        <>
          {o.has_video && (
            <section className="client-card video-card">
              <video src={`${o.video_url}#t=0.1`} controls playsInline preload="metadata" />
              <a className="client-btn" href={o.video_url} download>
                Baixar vídeo
              </a>
            </section>
          )}

          {o.feedback && (
            <section className="client-card">
              <h2>Devolutiva do treinador</h2>
              {o.feedback.summary && <p className="fb-summary">{o.feedback.summary}</p>}
              <FbList title="Pontos fortes" items={o.feedback.strengths} kind="good" />
              <FbList title="O que melhorar" items={o.feedback.improve} kind="improve" />
              <FbList title="Exercícios sugeridos" items={o.feedback.drills} kind="drill" />
            </section>
          )}

          {o.table && (
            <section className="client-card">
              <h2>Números</h2>
              {o.lead && <p>{o.lead}</p>}
              <div className="table-wrap">
                <table className="client-table">
                  <thead>
                    <tr>{o.table.head.map((h) => <th key={h}>{h}</th>)}</tr>
                  </thead>
                  <tbody>
                    {o.table.rows.map((r, i) => (
                      <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {(o.notes ?? []).length > 0 && (
                <ul className="muted small notes">
                  {o.notes!.map((n) => <li key={n}>{n}</li>)}
                </ul>
              )}
            </section>
          )}

          <section className="client-actions">
            <a className="client-btn" href={o.report_url} target="_blank" rel="noreferrer">
              Relatório completo (PDF)
            </a>
            <a className="client-btn ghost" href={share} target="_blank" rel="noreferrer">
              Compartilhar no WhatsApp
            </a>
          </section>
        </>
      )}
      <p className="muted small center">
        Fluxi Swim · <a href="https://swim.fluxiia.com">swim.fluxiia.com</a>
      </p>
    </div>
  );
}

function FbList(p: { title: string; items: string[]; kind: string }) {
  if (!p.items?.length) return null;
  return (
    <div className={`fb ${p.kind}`}>
      <h3>{p.title}</h3>
      <ul>
        {p.items.map((x) => <li key={x}>{x}</li>)}
      </ul>
    </div>
  );
}
