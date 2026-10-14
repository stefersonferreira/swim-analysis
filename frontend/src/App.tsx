import { useEffect, useState } from "react";
import VideoList from "./pages/VideoList";
import Upload from "./pages/Upload";
import Review from "./pages/Review";
import Login from "./pages/Login";
import SendVideo from "./pages/client/SendVideo";
import Delivery from "./pages/client/Delivery";
import { api } from "./api";

export function navigate(path: string) {
  window.history.pushState({}, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export function Link(props: { to: string; className?: string; children: React.ReactNode }) {
  return (
    <a
      href={props.to}
      className={props.className}
      onClick={(e) => {
        if (e.metaKey || e.ctrlKey) return;
        e.preventDefault();
        navigate(props.to);
      }}
    >
      {props.children}
    </a>
  );
}

function usePath() {
  const [path, setPath] = useState(window.location.pathname);
  useEffect(() => {
    const on = () => setPath(window.location.pathname);
    window.addEventListener("popstate", on);
    return () => window.removeEventListener("popstate", on);
  }, []);
  return path;
}

export default function App() {
  const path = usePath();
  // páginas do cliente: públicas, sem a barra do treinador
  if (path === "/enviar") return <SendVideo />;
  const share = path.match(/^\/r\/([A-Za-z0-9_-]+)/);
  if (share) return <Delivery token={share[1]} key={share[1]} />;
  return <CoachApp path={path} />;
}

function CoachApp({ path }: { path: string }) {
  const [auth, setAuth] = useState<{ auth_required: boolean; logged_in: boolean } | null>(null);
  const check = () => api.me().then(setAuth).catch(() => setAuth({ auth_required: false, logged_in: true }));
  useEffect(() => {
    void check();
    const on = () => setAuth((a) => (a ? { ...a, logged_in: false } : a));
    window.addEventListener("swim:login", on);
    return () => window.removeEventListener("swim:login", on);
  }, []);

  if (!auth) return <div className="page muted">Carregando…</div>;
  if (auth.auth_required && !auth.logged_in) return <Login onDone={() => void check()} />;

  const review = path.match(/^\/videos\/([0-9a-f]+)/);
  let page: React.ReactNode;
  if (review) page = <Review videoId={review[1]} key={review[1]} />;
  else if (path === "/upload") page = <Upload />;
  else page = <VideoList />;

  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand">
          Fluxi Swim · Análises
        </Link>
        <nav>
          <Link to="/">Pedidos</Link>
          <Link to="/upload">Enviar vídeo</Link>
          <a href="/enviar" target="_blank" rel="noreferrer">
            Página do cliente ↗
          </a>
          {auth.auth_required && (
            <button
              className="link"
              onClick={() => void api.logout().then(() => setAuth({ ...auth, logged_in: false }))}
            >
              Sair
            </button>
          )}
        </nav>
      </header>
      <main>{page}</main>
    </div>
  );
}
