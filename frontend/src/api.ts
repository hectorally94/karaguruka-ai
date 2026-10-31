export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T>(path: string, options: { method?: string; json?: unknown; form?: FormData } = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method: options.method ?? (options.json !== undefined || options.form ? "POST" : "GET"),
      headers: options.json !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: options.form ?? (options.json !== undefined ? JSON.stringify(options.json) : undefined),
    });
  } catch {
    throw new ApiError(0, "Le serveur est injoignable. Vérifiez que le backend est démarré.");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = typeof body?.detail === "string" ? body.detail : "La demande a échoué. Réessayez.";
    throw new ApiError(response.status, detail);
  }
  return response.json();
}

export type Source = { document_id: string; title: string; page: number | null };
export type Role = "admin" | "agent" | null;

export type ChatReply = {
  conversation_id: string;
  reply: string;
  chips: string[];
  intent: string;
  sources: Source[];
  masked: string[];
  ticket_ref: string | null;
  transferred: boolean;
};

export type StoredMessage = { id: number; role: "user" | "assistant" | "agent"; content: string; sources: Source[] | null; created_at: string };

export type DocumentRow = {
  id: string;
  title: string;
  filename: string;
  size_bytes: number;
  category: string;
  audience: "public" | "internal";
  status: "processing" | "ready" | "failed";
  error: string | null;
  active: boolean;
  effective_from: string | null;
  expires_at: string | null;
  version: number;
  page_count: number | null;
  chunk_count: number;
  used_ocr: boolean;
  updated_at: string;
};

export type Ticket = {
  id: string;
  ref: string;
  conversation_id: string;
  kind: string;
  department: string;
  priority: "P1" | "P2" | "P3";
  status: "open" | "in_progress" | "resolved";
  summary: string;
  contact: string | null;
  created_at: string;
  sentiment: string;
  channel: string;
  is_example: boolean;
  messages?: StoredMessage[];
};

export type AskResult = {
  found: boolean;
  route: string;
  answer: string;
  sources: Source[];
  excerpts: { title: string; page: number | null; content: string; coverage: number; similarity: number | null }[];
  mode: "claude" | "extrait";
};

export type Stats = {
  conversations: number;
  examples: number;
  handled_by_ai: number;
  transferred: number;
  voice: number;
  handle_minutes: number;
  minutes_saved: number;
  by_intent: { intent: string; count: number }[];
  by_day: { day: string; count: number }[];
  tickets: { open: number; in_progress: number; resolved: number; urgent: number };
  unanswered: number;
  documents: { ready: number; total: number };
};

export const INTENT_LABELS: Record<string, string> = {
  information: "Information",
  carte: "Carte",
  carte_perdue: "Carte perdue ou volée",
  fraude: "Fraude",
  credit: "Crédit",
  reclamation: "Réclamation",
  transfert: "Transfert vers un agent",
  sans_reponse: "Sans réponse",
  accueil: "Accueil",
  remerciement: "Remerciement",
  securite: "Sécurité",
  "non classé": "Non classé",
};

export const sourceLabel = (s: Source) => (s.page ? `${s.title}, page ${s.page}` : s.title);
