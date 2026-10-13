import { useEffect, useState } from "react";
import VideoList from "./pages/VideoList";
import Upload from "./pages/Upload";
import Review from "./pages/Review";

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
  const review = path.match(/^\/videos\/([0-9a-f]+)/);
  let page: React.ReactNode;
  if (review) page = <Review videoId={review[1]} key={review[1]} />;
  else if (path === "/upload") page = <Upload />;
  else page = <VideoList />;

  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand">
          Análise de Provas
        </Link>
        <nav>
          <Link to="/">Provas</Link>
          <Link to="/upload">Enviar vídeo</Link>
        </nav>
      </header>
      <main>{page}</main>
    </div>
  );
}
