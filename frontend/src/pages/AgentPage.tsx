import { type FormEvent, useCallback, useEffect, useState } from "react";
import { api, ApiError, type AskResult, INTENT_LABELS, type Source, sourceLabel, type Ticket } from "../api";

type Suggestion = {
  reply: string;
  sources: Source[];
  internal_references: { title: string; page: number | null; content: string }[];
};

const PRIORITY: Record<string, { label: string; cls: string }> = {
  P1: { label: "P1 Urgent", cls: "bg-urgent-soft text-urgent" },
  P2: { label: "P2 Normal", cls: "bg-warn-soft text-warn" },
  P3: { label: "P3 À rappeler", cls: "bg-brand-soft text-ink" },
};
const STATUS: Record<string, string> = { open: "En attente", in_progress: "En cours", resolved: "Clôturé" };
const ROLE_LABEL: Record<string, string> = { user: "Client", assistant: "Assistant", agent: "Conseiller" };

const time = (iso: string) => new Date(iso).toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

export default function AgentPage() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [draft, setDraft] = useState("");
  const [suggestion, setSuggestion] = useState<Suggestion | null>(null);
  const [suggesting, setSuggesting] = useState(false);
  const [error, setError] = useState("");
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<AskResult | null>(null);
  const [searching, setSearching] = useState(false);

  const load = useCallback(async () => {
    try {
      setTickets(await api<Ticket[]>("/tickets"));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "La file n'a pas pu être chargée.");
    }
  }, []);

  const loadTicket = useCallback(async (id: string) => {
    try {
      setTicket(await api<Ticket>(`/tickets/${id}`));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Le dossier n'a pas pu être chargé.");
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 4000);
    return () => clearInterval(timer);
  }, [load]);

  useEffect(() => {
    setSuggestion(null);
    setDraft("");
    if (!selectedId) return setTicket(null);
    void loadTicket(selectedId);
    const timer = setInterval(() => void loadTicket(selectedId), 4000);
    return () => clearInterval(timer);
  }, [selectedId, loadTicket]);

  const act = async (path: string, json?: unknown) => {
    if (!selectedId) return;
    setError("");
    try {
      await api(`/tickets/${selectedId}/${path}`, json ? { json } : { method: "POST" });
      await Promise.all([load(), loadTicket(selectedId)]);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "L'action a échoué.");
    }
  };

  const sendReply = async (event: FormEvent) => {
    event.preventDefault();
    if (!draft.trim()) return;
    await act("reply", { message: draft.trim() });
    setDraft("");
    setSuggestion(null);
  };

  const suggest = async () => {
    if (!selectedId) return;
    setSuggesting(true);
    setError("");
    try {
      const body = await api<Suggestion>(`/tickets/${selectedId}/suggest`, { method: "POST" });
      setSuggestion(body);
      if (!body.reply) setError("Aucun document public ne permet de proposer une réponse pour ce dossier.");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "La suggestion a échoué.");
    } finally {
      setSuggesting(false);
    }
  };

  const search = async (event: FormEvent) => {
    event.preventDefault();
    if (!question.trim()) return;
    setSearching(true);
    try {
      setResult(await api<AskResult>("/agent/search", { json: { question } }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "La recherche a échoué.");
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="grid flex-1 gap-5 lg:grid-cols-[320px_minmax(0,1fr)]">
      <section className="min-w-0 rounded-lg border border-line bg-surface" aria-label="File d'attente">
        <div className="border-b border-line px-4 py-3">
          <h1 className="text-lg font-bold">File d'attente</h1>
          <p className="text-sm text-muted">{tickets.length} dossier(s) à traiter</p>
        </div>
        <ul className="max-h-[70dvh] divide-y divide-line overflow-y-auto">
          {tickets.length === 0 && <li className="p-4 text-sm text-muted">Aucun dossier en attente. Les transferts de l'assistant apparaîtront ici.</li>}
          {tickets.map((t) => (
            <li key={t.id}>
              <button onClick={() => setSelectedId(t.id)} className={`w-full px-4 py-3 text-left hover:bg-sunken ${selectedId === t.id ? "bg-brand-soft" : ""}`}>
                <div className="flex items-center gap-2">
                  <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${PRIORITY[t.priority].cls}`}>{PRIORITY[t.priority].label}</span>
                  <span className="font-mono text-xs text-muted">{t.ref}</span>
                  {t.is_example && <span className="ml-auto text-xs text-muted">Exemple</span>}
                </div>
                <p className="mt-1 text-sm font-medium">{t.department}</p>
                <p className="line-clamp-2 text-sm text-muted">{t.summary}</p>
                <p className="mt-1 text-xs text-muted">{STATUS[t.status]} · {time(t.created_at)}</p>
              </button>
            </li>
          ))}
        </ul>
      </section>

      <div className="flex min-w-0 flex-col gap-5">
        {error && <p role="alert" className="rounded-md bg-urgent-soft px-3 py-2 text-sm text-urgent">{error}</p>}

        <section className="rounded-lg border border-line bg-surface" aria-label="Dossier">
          {!ticket ? (
            <p className="p-6 text-muted">Sélectionnez un dossier pour voir son résumé et sa conversation.</p>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-3">
                <h2 className="font-bold"><span className="font-mono">{ticket.ref}</span> · {INTENT_LABELS[ticket.kind] ?? ticket.kind}</h2>
                <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${PRIORITY[ticket.priority].cls}`}>{PRIORITY[ticket.priority].label}</span>
                {ticket.sentiment === "frustré" && <span className="rounded bg-warn-soft px-1.5 py-0.5 text-xs font-medium text-warn">Client frustré</span>}
                <div className="ml-auto flex gap-2">
                  {ticket.status === "open" && <button onClick={() => void act("take")} className="rounded-md bg-brand px-3 py-1.5 text-sm font-medium text-brand-ink">Prendre en charge</button>}
                  {ticket.status !== "resolved" && <button onClick={() => void act("resolve")} className="rounded-md border border-line px-3 py-1.5 text-sm">Clôturer</button>}
                </div>
              </div>
              <div className="border-b border-line bg-sunken px-4 py-3 text-sm">
                <p className="font-semibold">Résumé <span className="font-normal text-muted">(généré d'après les propos du client, à vérifier)</span></p>
                <p className="mt-1">{ticket.summary}</p>
                {ticket.contact && <p className="mt-1 text-muted">À rappeler au <span className="font-mono">{ticket.contact}</span></p>}
              </div>
              <div className="max-h-80 space-y-2 overflow-y-auto p-4">
                {ticket.messages?.map((m) => (
                  <div key={m.id} className="text-sm">
                    <span className={`font-semibold ${m.role === "user" ? "text-brand" : m.role === "agent" ? "text-good" : "text-muted"}`}>{ROLE_LABEL[m.role]}</span>
                    <span className="ml-2 text-xs text-muted">{time(m.created_at)}</span>
                    <p className="whitespace-pre-line">{m.content}</p>
                  </div>
                ))}
              </div>
              {ticket.status !== "resolved" && (
                <div className="border-t border-line p-4">
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <button onClick={() => void suggest()} disabled={suggesting} className="rounded-md border border-brand px-3 py-1.5 text-sm text-brand disabled:opacity-50">
                      {suggesting ? "Recherche…" : "Suggérer une réponse"}
                    </button>
                    {suggestion?.reply && <button onClick={() => setDraft(suggestion.reply)} className="text-sm text-brand underline">Utiliser cette suggestion</button>}
                  </div>
                  {suggestion?.reply && (
                    <div className="mb-3 rounded-md bg-brand-soft p-3 text-sm">
                      <p className="whitespace-pre-line">{suggestion.reply}</p>
                      {suggestion.sources.length > 0 && <p className="mt-1 text-xs text-muted">Source : {suggestion.sources.map(sourceLabel).join(" ; ")}</p>}
                      <p className="mt-1 text-xs text-muted">Relisez avant d'envoyer : cette suggestion s'appuie sur des propos écrits par le client.</p>
                    </div>
                  )}
                  {!!suggestion?.internal_references.length && (
                    <div className="mb-3 rounded-md bg-warn-soft p-3 text-sm">
                      <p className="font-semibold text-warn">Interne : ne pas communiquer au client</p>
                      {suggestion.internal_references.map((r) => (
                        <div key={`${r.title}-${r.content.slice(0, 20)}`} className="mt-2">
                          <p className="font-medium">{r.title}{r.page ? `, page ${r.page}` : ""}</p>
                          <p className="whitespace-pre-line">{r.content}</p>
                        </div>
                      ))}
                    </div>
                  )}
                  <form onSubmit={(e) => void sendReply(e)} className="flex gap-2">
                    <label htmlFor="reply" className="sr-only">Réponse au client</label>
                    <textarea id="reply" rows={2} value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Votre réponse au client" className="min-w-0 flex-1 rounded-md border border-line bg-page px-3 py-2" />
                    <button disabled={!draft.trim()} className="self-end rounded-md bg-brand px-4 py-2 font-medium text-brand-ink disabled:opacity-50">Envoyer</button>
                  </form>
                </div>
              )}
            </>
          )}
        </section>

        <section className="rounded-lg border border-line bg-surface p-4" aria-label="Recherche documentaire">
          <h2 className="font-bold">Chercher dans les documents</h2>
          <p className="text-sm text-muted">Inclut les procédures internes, invisibles pour les clients.</p>
          <form onSubmit={(e) => void search(e)} className="mt-3 flex gap-2">
            <label htmlFor="agent-question" className="sr-only">Question</label>
            <input id="agent-question" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Ex. : vérifications avant une opposition" className="min-w-0 flex-1 rounded-md border border-line bg-page px-3 py-2" />
            <button disabled={searching} className="rounded-md border border-line px-4 py-2 disabled:opacity-50">Chercher</button>
          </form>
          {result && (
            <div className="mt-3 text-sm">
              <p className="whitespace-pre-line">{result.found ? result.answer : "Aucun document ne répond à cette question."}</p>
              {result.sources.length > 0 && <p className="mt-1 text-xs text-muted">Source : {result.sources.map(sourceLabel).join(" ; ")}</p>}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
