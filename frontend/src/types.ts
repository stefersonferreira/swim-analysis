export type Stroke = "freestyle" | "breaststroke";

export type EventType =
  | "start_signal"
  | "feet_off"
  | "entry"
  | "breakout"
  | "stroke"
  | "wall_hands"
  | "wall_feet"
  | "finish_touch"
  | "mark_pass";

export interface RaceInfo {
  stroke: Stroke;
  distance: number;
  pool_length: number;
  lane?: number | null;
  cap_color?: string | null;
  official_final_s?: number | null;
  official_splits_s?: number[];
}

export interface VideoMeta {
  width: number;
  height: number;
  proxy_width: number;
  proxy_height: number;
  fps_nominal: number;
  fps_measured: number;
  variable_frame_rate: boolean;
  n_frames: number;
  duration_s: number;
  has_audio: boolean;
}

export interface Video {
  id: string;
  title: string;
  athlete: string | null;
  status: "uploaded" | "processing" | "ready" | "rejected" | "failed";
  error: string | null;
  warnings: string[];
  race: RaceInfo;
  meta: VideoMeta | null;
  has_calibration: boolean;
  calibration_ok: boolean;
  analysis_status: "idle" | "queued" | "running" | "done" | "failed";
  analysis_notes: string[];
  analyzed_at: string | null;
  created_at: string | null;
}

export interface SwimEvent {
  id: string;
  type: EventType;
  frame: number;
  t: number;
  image_xy: [number, number] | null;
  mark_m: number | null;
  x_m: number | null;
  confidence: number;
  source: "auto" | "manual";
}

export interface Metric {
  name: string;
  value: number | null;
  unit: string;
  length_index: number | null;
  turn_index: number | null;
  status: "ok" | "not_measured";
  reason: string | null;
  source: "measured" | "official";
}

export interface Alert {
  kind: string;
  message: string;
  length_index: number | null;
  t_from: number | null;
  t_to: number | null;
  event_ids: string[];
}

export interface ReviewState {
  events: SwimEvent[];
  metrics: Metric[];
  alerts: Alert[];
  race: RaceInfo;
}

export interface PoolProfile {
  name?: string;
  length_m: number;
  lanes: number;
  lane_width_m: number;
  marks_m: number[];
}

export interface ClickPoint {
  image_xy: [number, number];
  pool_xy: [number, number];
  label?: string | null;
}

export interface Anchor {
  frame: number;
  points: ClickPoint[];
}

export interface AnchorResult {
  frame: number;
  homography: number[][] | null;
  mean_error_m: number | null;
  max_error_m: number | null;
  point_errors_m: number[];
  inliers: boolean[];
  accepted: boolean;
  message: string | null;
}

export interface GridLine {
  kind: "x" | "rope";
  value: number;
  points: [number, number][];
}

export interface CalibrationState {
  calibration: { pool: PoolProfile; anchors: Anchor[]; results: AnchorResult[] };
  grids: Record<string, GridLine[]>;
}

export interface TrajectoryData {
  frame: number[];
  head_x: number[];
  confidence: number[];
  head_img_x: number[];
  head_img_y: number[];
}
