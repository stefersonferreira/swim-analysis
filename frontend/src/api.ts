import type {
  Anchor,
  CalibrationState,
  EventType,
  GridLine,
  PoolProfile,
  Feedback,
  OrderStatus,
  PublicOrder,
  RaceInfo,
  ReviewState,
  TechNote,
  TechState,
  TrajectoryData,
  Video,
} from "./types";
import type { OverlayTimeline } from "./overlay/state";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: init?.body && !(init.body instanceof FormData)
      ? { "Content-Type": "application/json", ...(init?.headers || {}) }
      : init?.headers,
  });
  if (res.status === 401 && !path.startsWith("/api/auth/")) {
    window.dispatchEvent(new Event("swim:login"));
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* resposta sem JSON */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  me: () => req<{ auth_required: boolean; logged_in: boolean }>("/api/auth/me"),
  login: (password: string) =>
    req<{ logged_in: boolean }>("/api/auth/login", { method: "POST", body: JSON.stringify({ password }) }),
  logout: () => req<{ logged_in: boolean }>("/api/auth/logout", { method: "POST" }),
  updateOrder: (
    id: string,
    body: { status?: OrderStatus; paid?: boolean; customer_name?: string; customer_email?: string; customer_phone?: string },
  ) => req<Video>(`/api/videos/${id}/order`, { method: "PUT", body: JSON.stringify(body) }),
  saveFeedback: (id: string, fb: Feedback) =>
    req<Video>(`/api/videos/${id}/feedback`, { method: "PUT", body: JSON.stringify(fb) }),
  draftFeedback: (id: string) => req<Feedback>(`/api/videos/${id}/feedback/draft`, { method: "POST" }),
  deliver: (id: string) => req<Video>(`/api/videos/${id}/deliver`, { method: "POST" }),
  technique: (id: string) => req<TechState>(`/api/videos/${id}/technique`),
  saveTechnique: (id: string, notes: TechNote[]) =>
    req<Video & { tech_notes: TechNote[] }>(`/api/videos/${id}/technique`, { method: "PUT", body: JSON.stringify(notes) }),
  techAI: (id: string, body: { frame: number; phase: string; lane: number | null; mark: [number, number] | null }) =>
    req<{ items: string[]; text: string; visible: boolean; confidence: number }>(`/api/videos/${id}/technique/ai`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  publicOrder: (token: string) => req<PublicOrder>(`/api/public/r/${token}`),
  listVideos: () => req<Video[]>("/api/videos"),
  getVideo: (id: string) => req<Video>(`/api/videos/${id}`),
  deleteVideo: (id: string) => req<void>(`/api/videos/${id}`, { method: "DELETE" }),
  reingest: (id: string) => req<Video>(`/api/videos/${id}/reingest`, { method: "POST" }),
  updateRace: (id: string, race: RaceInfo) =>
    req<Video>(`/api/videos/${id}/race`, { method: "PUT", body: JSON.stringify(race) }),
  frames: (id: string) => req<{ pts: number[] }>(`/api/videos/${id}/frames.json`),
  waveform: (id: string) =>
    req<{ bins_per_s: number; peaks: number[] }>(`/api/videos/${id}/waveform.json`),
  events: (id: string) => req<ReviewState>(`/api/videos/${id}/events`),
  patchEvents: (
    id: string,
    body: {
      create?: {
        type: EventType;
        frame: number;
        image_xy?: [number, number] | null;
        mark_m?: number | null;
        lane?: number | null;
      }[];
      update?: {
        id: string;
        frame?: number;
        type?: EventType;
        image_xy?: [number, number] | null;
        clear_image_xy?: boolean;
        mark_m?: number | null;
        lane?: number | null;
        clear_lane?: boolean;
      }[];
      delete?: string[];
    },
  ) =>
    req<ReviewState & { created_ids: string[] }>(`/api/videos/${id}/events`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  calibration: (id: string) => req<CalibrationState>(`/api/videos/${id}/calibration`),
  saveCalibration: (id: string, pool: PoolProfile, anchors: Anchor[]) =>
    req<CalibrationState & ReviewState & { video: Video }>(`/api/videos/${id}/calibration`, {
      method: "PUT",
      body: JSON.stringify({ pool, anchors }),
    }),
  copyCalibration: (id: string, from: string) =>
    req<CalibrationState & ReviewState & { video: Video }>(`/api/videos/${id}/calibration/copy-from/${from}`, {
      method: "POST",
    }),
  worker: () => req<Record<string, unknown>>("/api/system/worker"),
  analyze: (id: string) => req<Video>(`/api/videos/${id}/analyze`, { method: "POST" }),
  updateFinalOptions: (id: string, opts: { strokes_partial: boolean; notes: string[] }) =>
    req<Video>(`/api/videos/${id}/final-options`, { method: "PUT", body: JSON.stringify(opts) }),
  exportVideo: (id: string) => req<Video>(`/api/videos/${id}/export`, { method: "POST" }),
  trajectory: (id: string) =>
    req<{ frames: TrajectoryData | [] }>(`/api/videos/${id}/trajectory.json`),
  overlay: (id: string) => req<OverlayTimeline>(`/api/videos/${id}/overlay.json`),
  grid: (id: string, frame: number) =>
    req<{ lines: GridLine[] }>(`/api/videos/${id}/grid/${frame}`),
};

export function frameUrl(id: string, n: number) {
  return `/api/videos/${id}/frames/${n}.jpg`;
}

export function upload(
  form: FormData,
  onProgress: (fraction: number) => void,
): Promise<Video> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/videos");
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onload = () => {
      try {
        const body = JSON.parse(xhr.responseText);
        if (xhr.status >= 200 && xhr.status < 300) resolve(body);
        else reject(new Error(body.detail || xhr.statusText));
      } catch {
        reject(new Error(xhr.statusText || "falha no envio"));
      }
    };
    xhr.onerror = () => reject(new Error("falha de rede no envio"));
    xhr.send(form);
  });
}
