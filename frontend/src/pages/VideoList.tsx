import { useEffect, useState } from "react";
import { api } from "../api";
import { Link } from "../App";
import { STROKE_LABEL } from "../labels";
import type { OrderStatus, Video } from "../types";

const ORDER: Record<OrderStatus, string> = { new: "Novo", reviewing: "Em análise", delivered: "Entregue" };

/** "faltam 41 h" / "atrasado 3 h" */
export function dueText(due: string | null, now = Date.now()): { text: string; late: boolean } | null {
  if (!due) return null;
  const h = (new Date(due).getTime() - now) / 3_600_000;
  if (h < 0) return { text: `atrasado ${Math.ceil(-h)} h`, late: true };
  return { text: h < 1 ? "falta < 1 h" : `faltam ${Math.floor(h)} h`, late: false };
}

const STATUS: Record<Video["status"], string> = {
  uploaded: "Na fila",
  processing: "Processando",
  ready: "Pronto",
  rejected: "Recusado",
  failed: "Falhou",
};

export default function VideoList() {
  const [videos, setVideos] = useState<Video[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [worker, setWorker] = useState<Record<string, unknown> | null>(null);
  const [tab, setTab] = useState<"open" | "delivered" | "all">("open");

  useEffect(() => {
    let alive = true;
    const load = () =>
      api
        .listVideos()
        .then((v) => alive && setVideos(v))
        .catch((e) => alive && setError(String(e.message || e)));
    load();
    const busy = setInterval(load, 3000);
    api.worker().then((w) => alive && setWorker(w)).catch(() => undefined);
    return () => {
      alive = false;
      clearInterval(busy);
    };
  }, []);

  return (
    <div className="page">
      <div className="page-head">
        <h1>Pedidos e provas</h1>
        <Link to="/upload" className="btn primary">
          Enviar vídeo
        </Link>
      </div>
      {worker && (
        <p className="muted small">
          Processamento: {worker.worker === "offline" ? "worker fora do ar" : "worker ativo"}
          {" · "}
          {worker.gpu ? `GPU ${String(worker.nvidia_smi ?? "")}` : "sem GPU (CPU)"}
        </p>
      )}
      {error && <p className="error">{error}</p>}
      {videos && videos.length === 0 && (
        <div className="empty">
          <p>Nenhuma prova ainda.</p>
          <Link to="/upload" className="btn">
            Enviar o primeiro vídeo
          </Link>
        </div>
      )}
      {videos && videos.length > 0 && (
        <>
          <div className="tabs list-tabs">
            {([["open", "Abertos"], ["delivered", "Entregues"], ["all", "Todos"]] as const).map(([k, l]) => (
              <button key={k} className={tab === k ? "active" : ""} onClick={() => setTab(k)}>
                {l} ({videos.filter((v) => k === "all" || (k === "delivered") === (v.order.status === "delivered")).length})
              </button>
            ))}
          </div>
          <table className="list">
            <thead>
              <tr>
                <th>Pedido</th>
                <th>Prova</th>
                <th>Prazo</th>
                <th>Situação</th>
                <th>Pago</th>
                <th>Vídeo</th>
                <th>Recebido</th>
              </tr>
            </thead>
            <tbody>
              {sortOrders(videos)
                .filter((v) => tab === "all" || (tab === "delivered") === (v.order.status === "delivered"))
                .map((v) => {
                  const due = v.order.status === "delivered" ? null : dueText(v.order.due_at);
                  return (
                    <tr key={v.id}>
                      <td>
                        {v.status === "ready" ? <Link to={`/videos/${v.id}`}>{v.title}</Link> : v.title}
                        <div className="muted small">
                          {v.order.origin === "client" ? "Cliente" : "Treinador"}
                          {v.order.customer_name ? ` · ${v.order.customer_name}` : v.athlete ? ` · ${v.athlete}` : ""}
                          {v.order.customer_phone ? ` · ${v.order.customer_phone}` : ""}
                        </div>
                        {v.order.customer_notes && <div className="small notes-cell">“{v.order.customer_notes}”</div>}
                        {v.error && <div className="error small">{v.error}</div>}
                      </td>
                      <td>
                        {STROKE_LABEL[v.race.stroke]} · {v.race.distance} m
                        <div className="muted small">piscina {v.race.pool_length} m</div>
                      </td>
                      <td className={due?.late ? "late" : "muted"}>
                        {v.order.status === "delivered" && v.order.delivered_at
                          ? `entregue ${new Date(v.order.delivered_at).toLocaleDateString("pt-BR")}`
                          : due?.text ?? "—"}
                      </td>
                      <td>
                        <span className={`ostatus ${v.order.status}`}>{ORDER[v.order.status]}</span>
                      </td>
                      <td>
                        <label className="paid">
                          <input
                            type="checkbox"
                            checked={v.order.paid}
                            onChange={async (e) => {
                              const nv = await api.updateOrder(v.id, { paid: e.target.checked });
                              setVideos((vs) => vs && vs.map((x) => (x.id === v.id ? nv : x)));
                            }}
                          />
                        </label>
                      </td>
                      <td>
                        <span className={`status ${v.status}`}>{STATUS[v.status]}</span>
                      </td>
                      <td className="muted">
                        {v.created_at ? new Date(v.created_at).toLocaleString("pt-BR") : ""}
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

/** Abertos primeiro, pelo prazo mais próximo; depois os sem prazo e os entregues, mais novos antes. */
export function sortOrders(vs: Video[]): Video[] {
  const key = (v: Video) =>
    v.order.status === "delivered" ? 2 : v.order.due_at ? 0 : 1;
  return [...vs].sort((a, b) => {
    const ka = key(a), kb = key(b);
    if (ka !== kb) return ka - kb;
    if (ka === 0) return new Date(a.order.due_at!).getTime() - new Date(b.order.due_at!).getTime();
    return new Date(b.created_at ?? 0).getTime() - new Date(a.created_at ?? 0).getTime();
  });
}
