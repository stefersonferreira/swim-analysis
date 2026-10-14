import { useState } from "react";
import { api } from "../api";

export default function Login({ onDone }: { onDone: () => void }) {
  const [pw, setPw] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const go = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.login(pw);
      onDone();
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="page login">
      <h1>Área do treinador</h1>
      <p className="muted">Entre com a senha para ver os pedidos e revisar os vídeos.</p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void go();
        }}
      >
        <input
          type="password"
          value={pw}
          onChange={(e) => setPw(e.target.value)}
          autoFocus
          autoComplete="current-password"
          placeholder="Senha"
          aria-label="Senha"
        />
        <button className="btn primary" disabled={!pw || busy}>
          {busy ? "Entrando…" : "Entrar"}
        </button>
      </form>
      {error && <p className="error">{error}</p>}
    </div>
  );
}
