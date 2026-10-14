import { useState } from "react";
import { navigate } from "../../App";
import "./client.css";

/**
 * Página pública: o atleta (ou o responsável) envia o vídeo pelo celular e recebe um link
 * para acompanhar a análise. Sem login.
 */
export default function SendVideo() {
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [stroke, setStroke] = useState<"freestyle" | "breaststroke">("freestyle");
  const [pool, setPool] = useState(25);
  const [distance, setDistance] = useState(25);
  const [notes, setNotes] = useState("");
  const [trap, setTrap] = useState("");
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [duration, setDuration] = useState<number | null>(null);

  const pick = (f: File | null) => {
    setFile(f);
    setDuration(null);
    if (!f) return;
    const v = document.createElement("video");
    v.preload = "metadata";
    v.onloadedmetadata = () => {
      setDuration(v.duration);
      URL.revokeObjectURL(v.src);
    };
    v.src = URL.createObjectURL(f);
  };

  const ok = file && name.trim().length >= 2 && (email.trim() || phone.trim());

  const send = () => {
    if (!file || !ok) return;
    setError(null);
    const fd = new FormData();
    fd.append("file", file);
    fd.append("name", name);
    fd.append("email", email);
    fd.append("phone", phone);
    fd.append("stroke", stroke);
    fd.append("pool_length", String(pool));
    fd.append("distance", String(distance));
    fd.append("notes", notes);
    fd.append("website", trap);
    // XHR para mostrar o progresso do envio (vídeos de celular são grandes)
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/public/orders");
    xhr.upload.onprogress = (e) => e.lengthComputable && setProgress(e.loaded / e.total);
    xhr.onload = () => {
      if (xhr.status === 201) {
        const out = JSON.parse(xhr.responseText) as { path: string };
        navigate(out.path + "?novo=1");
      } else {
        setProgress(null);
        let msg = "Não foi possível enviar. Tente de novo.";
        try {
          const d = JSON.parse(xhr.responseText).detail;
          if (typeof d === "string") msg = d;
        } catch {
          /* resposta sem JSON */
        }
        setError(msg);
      }
    };
    xhr.onerror = () => {
      setProgress(null);
      setError("Sem conexão. Confira a internet e tente de novo.");
    };
    setProgress(0);
    xhr.send(fd);
  };

  const sending = progress !== null;

  return (
    <div className="client">
      <header className="client-head">
        <div className="brand-word">Fluxi Swim</div>
        <h1>Análise do seu nado em vídeo</h1>
        <p className="lead">
          Envie um vídeo curto. Você recebe o vídeo com tempo, ritmo e cada ciclo marcado, mais a
          devolutiva escrita de um treinador.
        </p>
      </header>

      <section className="client-card">
        <h2>Como gravar</h2>
        <ol className="howto">
          <li><b>Celular deitado</b>, na lateral da piscina, de preferência apoiado ou num tripé.</li>
          <li><b>De 20 a 60 segundos</b>: comece antes do apito ou da saída e pare depois do toque.</li>
          <li><b>Sem zoom</b> e com o atleta sempre no quadro; dá para acompanhar girando o celular.</li>
          <li>Se houver mais gente na água, diga a <b>raia e a cor da touca</b> nas observações.</li>
        </ol>
      </section>

      <section className="client-card">
        <h2>Seu vídeo</h2>
        <label className={`file-drop ${file ? "has" : ""}`}>
          <input
            type="file"
            accept="video/mp4,video/quicktime,video/*"
            onChange={(e) => pick(e.target.files?.[0] ?? null)}
            disabled={sending}
          />
          {file ? (
            <>
              <b>{file.name}</b>
              <span>
                {(file.size / 1024 / 1024).toFixed(0)} MB
                {duration != null && ` · ${Math.round(duration)} s`}
              </span>
              <span className="muted">toque para trocar</span>
            </>
          ) : (
            <>
              <b>Escolher vídeo</b>
              <span className="muted">da galeria ou dos arquivos</span>
            </>
          )}
        </label>
        {duration != null && (duration < 10 || duration > 120) && (
          <p className="hint-warn">
            O vídeo tem {Math.round(duration)} s. O ideal é de 20 a 60 s, só com o trecho do nado.
          </p>
        )}

        <div className="seg-row">
          <span>Estilo</span>
          <div className="seg">
            {(["freestyle", "breaststroke"] as const).map((s) => (
              <button key={s} className={stroke === s ? "on" : ""} onClick={() => setStroke(s)} type="button">
                {s === "freestyle" ? "Livre (crawl)" : "Peito"}
              </button>
            ))}
          </div>
        </div>
        <div className="seg-row">
          <span>Piscina</span>
          <div className="seg">
            {[25, 50].map((p) => (
              <button
                key={p}
                type="button"
                className={pool === p ? "on" : ""}
                onClick={() => {
                  setPool(p);
                  if (distance % p) setDistance(p);
                }}
              >
                {p} m
              </button>
            ))}
          </div>
        </div>
        <div className="seg-row">
          <span>Distância no vídeo</span>
          <div className="seg">
            {[25, 50, 100]
              .filter((d) => d % pool === 0)
              .map((d) => (
                <button key={d} type="button" className={distance === d ? "on" : ""} onClick={() => setDistance(d)}>
                  {d} m
                </button>
              ))}
          </div>
        </div>
      </section>

      <section className="client-card">
        <h2>Seus dados</h2>
        <label className="field">
          Nome do atleta
          <input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" maxLength={200} />
        </label>
        <label className="field">
          WhatsApp
          <input value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="tel" autoComplete="tel" maxLength={40} />
        </label>
        <label className="field">
          E-mail
          <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" autoComplete="email" maxLength={200} />
        </label>
        <label className="field">
          Observações (opcional)
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={3}
            maxLength={1000}
            placeholder="O que quer melhorar? Raia e cor da touca, se houver mais gente."
          />
        </label>
        <input
          className="trap"
          tabIndex={-1}
          autoComplete="off"
          aria-hidden="true"
          value={trap}
          onChange={(e) => setTrap(e.target.value)}
          name="website"
        />
        <p className="muted small">Informe WhatsApp ou e-mail para receber o link da análise.</p>
      </section>

      {error && <p className="client-error">{error}</p>}
      <button className="client-cta" disabled={!ok || sending} onClick={send} data-testid="send">
        {sending ? `Enviando… ${Math.round(100 * (progress ?? 0))}%` : "Enviar para análise"}
      </button>
      {sending && (
        <div className="bar">
          <div style={{ width: `${100 * (progress ?? 0)}%` }} />
        </div>
      )}
      <p className="muted small center">Entrega em até 72 horas, pelo link que aparece ao terminar o envio.</p>
    </div>
  );
}
