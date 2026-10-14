import { useEffect, useRef } from "react";
import { frameUrl } from "../api";

/**
 * Mostra o quadro exato (imagem decodificada no servidor) quando pausado e o vídeo
 * durante a reprodução. O SVG por cima usa as coordenadas em pixels do proxy, as mesmas
 * gravadas nos eventos e na calibração.
 */
export default function FrameView(props: {
  videoId: string;
  width: number;
  height: number;
  frame: number;
  nFrames: number;
  playing: boolean;
  videoRef: React.RefObject<HTMLVideoElement>;
  onClick?: (x: number, y: number) => void;
  cursor?: string;
  children?: React.ReactNode;
  /** Camada HTML por cima do SVG (sobreposição ao vivo), sem receber cliques. */
  hud?: React.ReactNode;
}) {
  const { videoId, width, height, frame, nFrames, playing } = props;
  const svgRef = useRef<SVGSVGElement>(null);

  // Pré-carrega quadros vizinhos para o passo a passo ficar instantâneo.
  useEffect(() => {
    if (playing) return;
    const ids = [1, -1, 2, -2, 3, 5, 10, -10];
    const imgs = ids
      .map((d) => frame + d)
      .filter((n) => n >= 0 && n < nFrames)
      .map((n) => {
        const im = new Image();
        im.src = frameUrl(videoId, n);
        return im;
      });
    return () => imgs.forEach((im) => (im.src = ""));
  }, [frame, playing, videoId, nFrames]);

  function click(e: React.MouseEvent<SVGSVGElement>) {
    if (!props.onClick || !svgRef.current) return;
    const r = svgRef.current.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width) * width;
    const y = ((e.clientY - r.top) / r.height) * height;
    props.onClick(Math.round(x * 10) / 10, Math.round(y * 10) / 10);
  }

  return (
    <div className="frame" style={{ aspectRatio: `${width} / ${height}` }}>
      <video
        ref={props.videoRef}
        src={`/api/videos/${videoId}/proxy.mp4`}
        preload="auto"
        playsInline
        style={{ visibility: playing ? "visible" : "hidden" }}
      />
      {!playing && <img src={frameUrl(videoId, frame)} alt={`Quadro ${frame}`} draggable={false} />}
      <svg
        ref={svgRef}
        viewBox={`0 0 ${width} ${height}`}
        onClick={click}
        style={{ cursor: props.cursor ?? "default" }}
      >
        {props.children}
      </svg>
      {props.hud}
    </div>
  );
}
