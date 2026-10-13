import { useState } from "react";
import { upload } from "../api";
import { navigate } from "../App";
import RaceFields from "../components/RaceFields";
import type { RaceInfo } from "../types";

export default function Upload() {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [athlete, setAthlete] = useState("");
  const [race, setRace] = useState<RaceInfo>({
    stroke: "freestyle",
    distance: 50,
    pool_length: 25,
    lane: null,
    official_final_s: null,
    official_splits_s: [],
  });
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    form.append("race", JSON.stringify(race));
    form.append("title", title || file.name);
    form.append("athlete", athlete);
    setError(null);
    setProgress(0);
    try {
      await upload(form, setProgress);
      navigate("/");
    } catch (err) {
      setError(String((err as Error).message));
      setProgress(null);
    }
  }

  return (
    <div className="page narrow">
      <h1>Enviar vídeo</h1>
      <details className="guide">
        <summary>Como gravar para medir bem</summary>
        <ul>
          <li>Celular em 60 fps, 1080p ou mais, com o som ligado.</li>
          <li>Tripé ou apoio, na borda lateral ou arquibancada, a 2 m de altura ou mais.</li>
          <li>Comece a gravar antes do apito e só pare depois do toque final.</li>
          <li>Não use zoom durante a prova; mantenha a raia do nadador no quadro.</li>
          <li>De preferência, com a parede de saída e a marca de 15 m visíveis no início.</li>
        </ul>
      </details>
      <form onSubmit={submit} className="card">
        <label className="file">
          Vídeo da prova (MP4 ou MOV)
          <input
            type="file"
            accept="video/mp4,video/quicktime,.mp4,.mov,.m4v"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            required
          />
        </label>
        <div className="fields">
          <label>
            Nome da prova
            <input
              value={title}
              placeholder="ex.: Regional 50 livre"
              onChange={(e) => setTitle(e.target.value)}
            />
          </label>
          <label>
            Atleta
            <input value={athlete} onChange={(e) => setAthlete(e.target.value)} />
          </label>
        </div>
        <RaceFields race={race} onChange={setRace} />
        {error && <p className="error">{error}</p>}
        {progress != null ? (
          <div className="progress">
            <div style={{ width: `${Math.round(progress * 100)}%` }} />
            <span>{progress < 1 ? `Enviando ${Math.round(progress * 100)}%` : "Processando…"}</span>
          </div>
        ) : (
          <button className="btn primary" disabled={!file}>
            Enviar
          </button>
        )}
      </form>
    </div>
  );
}
