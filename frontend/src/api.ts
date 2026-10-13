import type {
  Anchor,
  CalibrationState,
  EventType,
  PoolProfile,
  RaceInfo,
  ReviewState,
  Video,
} from "./types";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: init?.body && !(init.body instanceof FormData)
      ? { "Content-Type": "application/json", ...(init?.headers || {}) }
      : init?.headers,
  });
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
      create?: { type: EventType; frame: number; image_xy?: [number, number] | null; mark_m?: number | null }[];
      update?: {
        id: string;
        frame?: number;
        type?: EventType;
        image_xy?: [number, number] | null;
        clear_image_xy?: boolean;
        mark_m?: number | null;
      }[];
      delete?: string[];
    },
  ) => req<ReviewState>(`/api/videos/${id}/events`, { method: "PATCH", body: JSON.stringify(body) }),
  calibration: (id: string) => req<CalibrationState>(`/api/videos/${id}/calibration`),
  saveCalibration: (id: string, pool: PoolProfile, anchors: Anchor[]) =>
    req<CalibrationState & ReviewState>(`/api/videos/${id}/calibration`, {
      method: "PUT",
      body: JSON.stringify({ pool, anchors }),
    }),
  copyCalibration: (id: string, from: string) =>
    req<CalibrationState & ReviewState>(`/api/videos/${id}/calibration/copy-from/${from}`, {
      method: "POST",
    }),
  worker: () => req<Record<string, unknown>>("/api/system/worker"),
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
