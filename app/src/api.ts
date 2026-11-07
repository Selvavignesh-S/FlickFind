import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";

// On a phone, set EXPO_PUBLIC_API_URL to the laptop's Tailscale address, e.g. http://100.x.y.z:8000
export const API_URL = process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000";

export type Status = "watchlist" | "watched" | "blocked";
export type BlockReason = "language" | "watched" | "theme" | "actor" | "mainstream" | "other";

export interface LibraryEntry {
  status: Status;
  rating: number | null;
  comment?: string | null;
  mood_match?: number | null;
  mindset?: string | null;
  block_reason: string | null;
  block_detail?: string | null;
}

export interface Film {
  tmdb_id: number;
  title: string;
  year: number | null;
  poster: string | null;
  overview?: string;
  tagline?: string | null;
  genres?: string[];
  language?: string;
  runtime?: number;
  director?: string[];
  cast?: string[];
  providers_in?: string[];
  mood_tags?: string[];
  effect?: string;
  watch_when?: string;
  why?: string; // the AI fit check's reason for this request
  fit?: number; // the AI fit check's score, 0-10
  ratings?: { imdb: number | null; rotten_tomatoes: number | null; flickfind: number | null; flickfind_votes: number };
  library: LibraryEntry | null;
  missing?: boolean; // left the catalog; only the saved title/year/poster remain
}

export interface Me {
  id: number;
  email: string;
  name: string;
  about: string;
  genres_like: string[];
  genres_avoid: string[];
  niche: number; // 0 = mainstream, 0.5 = no lean (new users), 1 = niche
  taste: "Mainstream" | "Balanced" | "Niche";
  niche_questions: boolean;
}

const KEY = "flickfind-token";
// shortcut: on web the token sits in localStorage (readable by any script on the page); fine for a local app,
// switch to an httpOnly cookie if the web app is ever hosted publicly
export const tokenStore = {
  get: async (): Promise<string | null> =>
    Platform.OS === "web" ? globalThis.localStorage?.getItem(KEY) ?? null : SecureStore.getItemAsync(KEY),
  set: async (t: string) => (Platform.OS === "web" ? localStorage.setItem(KEY, t) : SecureStore.setItemAsync(KEY, t)),
  clear: async () => (Platform.OS === "web" ? localStorage.removeItem(KEY) : SecureStore.deleteItemAsync(KEY)),
};

let token: string | null = null;
let onUnauthorized = () => {};
export const setToken = (t: string | null) => (token = t);
export const setUnauthorizedHandler = (f: () => void) => (onUnauthorized = f);

function errorText(data: unknown): string | null {
  const detail = (data as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg).join("; "); // FastAPI validation errors
  return null;
}

export async function api<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(API_URL + path, {
      method,
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new Error("Can't reach the FlickFind server. Is it running?");
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    if (res.status === 401 && token) onUnauthorized();
    throw new Error(errorText(data) ?? `Something went wrong (${res.status})`);
  }
  return data as T;
}
