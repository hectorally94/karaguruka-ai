import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, type ChatReply, INTENT_LABELS, type Source, sourceLabel, type StoredMessage } from "../api";

type Bubble = { key: string; role: "user" | "assistant" | "agent"; content: string; sources?: Source[] };
type Analysis = { intent: string; masked: string[]; sources: Source[]; ticketRef: string | null };

const STORAGE_KEY = "karaguruka_conversation";
const STARTERS = ["Carte bloquée", "Ouvrir un compte", "Informations crédit", "Faire une réclamation", "Horaires des agences", "Parler à un agent"];
const WELCOME: Bubble = { key: "welcome", role: "assistant", content: "Bonjour, je suis Karaguruka AI. Posez votre question ou choisissez une demande ci-dessous." };

/* eslint-disable @typescript-eslint/no-explicit-any */
const SpeechRecognitionApi: any = typeof window !== "undefined" ? (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition : undefined;

export default function AssistantPage() {
  const [conversationId, setConversationId] = useState<string | null>(() => sessionStorage.getItem(STORAGE_KEY));
  const [bubbles, setBubbles] = useState<Bubble[]>([WELCOME]);
  const [chips, setChips] = useState<string[]>(STARTERS);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [transferred, setTransferred] = useState(false);
  const [inCall, setInCall] = useState(false);
  const [listening, setListening] = useState(false);
  const [callStart, setCallStart] = useState<number | null>(null);
  const [now, setNow] = useState(Date.now());
  const [status, setStatus] = useState<{ claude: boolean; semantic_search: boolean } | null>(null);

  const seenAgent = useRef(new Set<number>());
  const inCallRef = useRef(false);
  const recognition = useRef<any>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const sendRef = useRef<(text: string, channel?: "text" | "voice") => Promise<void>>(async () => {});

  useEffect(() => {
    api<{ claude: boolean; semantic_search: boolean }>("/status").then(setStatus).catch(() => {});
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [bubbles, busy]);

  // Restores the conversation after a page reload.
  useEffect(() => {
    if (!conversationId) return;
    api<{ messages: StoredMessage[]; status: string }>(`/conversations/${conversationId}/messages`)
      .then(({ messages, status }) => {
        messages.filter((m) => m.role === "agent").forEach((m) => seenAgent.current.add(m.id));
        if (messages.length) {
          setBubbles([WELCOME, ...messages.map((m) => ({ key: String(m.id), role: m.role, content: m.content, sources: m.sources ?? [] }))]);
          setChips([]);
        }
        setTransferred(status === "transferred");
      })
      .catch(() => {
        sessionStorage.removeItem(STORAGE_KEY);
        setConversationId(null);
      });
    // Only needed once, for the id found at load.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const speak = useCallback((text: string, then?: () => void) => {
    if (!("speechSynthesis" in window)) return then?.();
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "fr-FR";
    utterance.onend = () => then?.();
    utterance.onerror = () => then?.();
    window.speechSynthesis.speak(utterance);
  }, []);

  const listen = useCallback(() => {
    if (!SpeechRecognitionApi || !inCallRef.current) return;
    const rec = new SpeechRecognitionApi();
    rec.lang = "fr-FR";
    rec.interimResults = false;
    rec.onstart = () => setListening(true);
    rec.onend = () => setListening(false);
    rec.onerror = (event: any) => {
      setListening(false);
      if (event.error === "not-allowed" || event.error === "service-not-allowed") {
        setError("Le micro est bloqué. Autorisez-le dans le navigateur, ou écrivez votre message.");
      }
    };
    rec.onresult = (event: any) => {
      const heard = event.results[0]?.[0]?.transcript;
      if (heard) void sendRef.current(heard, "voice");
    };
    recognition.current = rec;
    rec.start();
  }, []);

  const send = useCallback(
    async (text: string, channel: "text" | "voice" = "text") => {
      const message = text.trim();
      if (!message) return;
      setError("");
      setBusy(true);
      setChips([]);
      setInput("");
      const tempKey = `u${Date.now()}`;
      setBubbles((b) => [...b, { key: tempKey, role: "user", content: message }]);
      try {
        const body = await api<ChatReply>("/chat", { json: { conversation_id: conversationId, message, channel } });
        if (body.conversation_id !== conversationId) {
          setConversationId(body.conversation_id);
          sessionStorage.setItem(STORAGE_KEY, body.conversation_id);
        }
        // The server masks secrets before storing them. Secrets also disappear from the screen.
        if (body.masked.length) {
          const stored = await api<{ messages: StoredMessage[] }>(`/conversations/${body.conversation_id}/messages`);
          const safe = [...stored.messages].reverse().find((m) => m.role === "user")?.content;
          if (safe) setBubbles((b) => b.map((x) => (x.key === tempKey ? { ...x, content: safe } : x)));
        }
        setTransferred(body.transferred);
        setAnalysis({ intent: body.intent, masked: body.masked, sources: body.sources, ticketRef: body.ticket_ref });
        if (body.reply) {
          setBubbles((b) => [...b, { key: `a${Date.now()}`, role: "assistant", content: body.reply, sources: body.sources }]);
          setChips(body.chips);
          if (inCallRef.current) speak(body.reply, () => { if (!body.transferred) listen(); });
        }
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "Le message n'a pas pu être envoyé.");
        if (!conversationId) setChips(STARTERS);
      } finally {
        setBusy(false);
      }
    },
    [conversationId, listen, speak],
  );
  sendRef.current = send;

  // Agent replies arrive by polling while a person holds the conversation.
  useEffect(() => {
    if (!conversationId || !transferred) return;
    const timer = setInterval(async () => {
      try {
        const { messages, status } = await api<{ messages: StoredMessage[]; status: string }>(`/conversations/${conversationId}/messages`);
        const fresh = messages.filter((m) => m.role === "agent" && !seenAgent.current.has(m.id));
        fresh.forEach((m) => seenAgent.current.add(m.id));
        if (fresh.length) {
          setBubbles((b) => [...b, ...fresh.map((m) => ({ key: String(m.id), role: m.role, content: m.content }))]);
          if (inCallRef.current) speak(fresh[fresh.length - 1].content, listen);
        }
        if (status !== "transferred") setTransferred(false);
      } catch {
        // The next poll tries again.
      }
    }, 3000);
    return () => clearInterval(timer);
  }, [conversationId, transferred, speak, listen]);

  useEffect(() => {
    if (!inCall) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [inCall]);

  const startCall = () => {
    inCallRef.current = true;
    setInCall(true);
    setCallStart(Date.now());
    setNow(Date.now());
    speak("Bonjour, je suis Karaguruka AI. Comment puis-je vous aider ?", listen);
  };

  const endCall = () => {
    inCallRef.current = false;
    setInCall(false);
    setListening(false);
    recognition.current?.abort?.();
    window.speechSynthesis?.cancel();
  };

  const newConversation = () => {
    endCall();
    sessionStorage.removeItem(STORAGE_KEY);
    seenAgent.current.clear();
    setConversationId(null);
    setBubbles([WELCOME]);
    setChips(STARTERS);
    setAnalysis(null);
    setTransferred(false);
    setError("");
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void send(input);
  };

  const elapsed = callStart ? Math.floor((now - callStart) / 1000) : 0;
  const clock = `${String(Math.floor(elapsed / 60)).padStart(2, "0")}:${String(elapsed % 60).padStart(2, "0")}`;

  return (
    <div className="grid flex-1 gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
      <section className="flex min-h-[70dvh] min-w-0 flex-col rounded-lg border border-line bg-surface" aria-label="Conversation">
        <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3">
          <h1 className="text-lg font-bold">Banque Démo, service clients</h1>
          {inCall && (
            <span className="rounded-full bg-good-soft px-2.5 py-0.5 font-mono text-xs text-good tabular-nums">
              {listening ? "À l'écoute" : "En ligne"} {clock}
            </span>
          )}
          <div className="ml-auto flex flex-wrap gap-2">
            {SpeechRecognitionApi ? (
              inCall ? (
                <button onClick={endCall} className="rounded-md bg-urgent px-3 py-1.5 text-sm font-medium text-page">Raccrocher</button>
              ) : (
                <button onClick={startCall} className="rounded-md bg-brand px-3 py-1.5 text-sm font-medium text-brand-ink">Démarrer un appel</button>
              )
            ) : (
              <span className="text-xs text-muted">Pour l'appel vocal, ouvrez cette page dans Chrome.</span>
            )}
            <button onClick={newConversation} className="rounded-md border border-line px-3 py-1.5 text-sm">Nouvelle conversation</button>
          </div>
        </div>

        <div className="flex-1 space-y-3 overflow-y-auto p-4" aria-live="polite">
          {bubbles.map((bubble) => (
            <div key={bubble.key} className={`flex ${bubble.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[85%] rounded-lg px-3.5 py-2.5 ${bubble.role === "user" ? "bg-brand text-brand-ink" : bubble.role === "agent" ? "bg-good-soft" : "bg-sunken"}`}>
                {bubble.role === "agent" && <p className="mb-1 text-xs font-semibold text-good">Conseiller</p>}
                <p className="whitespace-pre-line">{bubble.content}</p>
                {!!bubble.sources?.length && (
                  <p className="mt-2 border-t border-line pt-1.5 text-xs text-muted">Source : {bubble.sources.map(sourceLabel).join(" ; ")}</p>
                )}
              </div>
            </div>
          ))}
          {busy && <p className="text-sm text-muted">L'assistant cherche la réponse…</p>}
          <div ref={endRef} />
        </div>

        {error && <p role="alert" className="mx-4 mb-2 rounded-md bg-urgent-soft px-3 py-2 text-sm text-urgent">{error}</p>}
        {transferred && <p className="mx-4 mb-2 rounded-md bg-warn-soft px-3 py-2 text-sm text-warn">Un conseiller a votre dossier et va vous répondre ici.</p>}

        {chips.length > 0 && (
          <div className="flex flex-wrap gap-2 px-4 pb-3">
            {chips.map((chip) => (
              <button key={chip} disabled={busy} onClick={() => void send(chip)} className="rounded-full border border-brand px-3 py-1 text-sm text-brand hover:bg-brand-soft disabled:opacity-50">
                {chip}
              </button>
            ))}
          </div>
        )}

        <form onSubmit={submit} className="flex gap-2 border-t border-line p-3">
          <label htmlFor="message" className="sr-only">Votre message</label>
          <input id="message" value={input} onChange={(e) => setInput(e.target.value)} maxLength={2000} placeholder="Écrivez votre question" className="min-w-0 flex-1 rounded-md border border-line bg-page px-3 py-2" />
          <button disabled={busy || !input.trim()} className="rounded-md bg-brand px-4 py-2 font-medium text-brand-ink disabled:opacity-50">Envoyer</button>
        </form>
      </section>

      <aside className="flex flex-col gap-4" aria-label="Analyse de la conversation">
        <div className="rounded-lg border border-line bg-surface p-4">
          <h2 className="font-bold">Ce que l'IA a compris</h2>
          {analysis ? (
            <dl className="mt-3 space-y-3 text-sm">
              <div>
                <dt className="text-muted">Demande</dt>
                <dd className="font-medium">{INTENT_LABELS[analysis.intent] ?? analysis.intent}</dd>
              </div>
              {analysis.ticketRef && (
                <div>
                  <dt className="text-muted">Dossier créé</dt>
                  <dd className="font-mono">{analysis.ticketRef}</dd>
                </div>
              )}
              {analysis.masked.length > 0 && (
                <div>
                  <dt className="text-muted">Données masquées</dt>
                  <dd className="text-urgent">{analysis.masked.join(", ")}</dd>
                </div>
              )}
              <div>
                <dt className="text-muted">Sources</dt>
                <dd>{analysis.sources.length ? analysis.sources.map(sourceLabel).join(" ; ") : "Aucune pour ce message"}</dd>
              </div>
            </dl>
          ) : (
            <p className="mt-2 text-sm text-muted">Envoyez un message pour voir la demande détectée, les sources et les données masquées.</p>
          )}
        </div>
        <div className="rounded-lg border border-line bg-surface p-4 text-sm">
          <h2 className="font-bold">Mode de réponse</h2>
          {status && (
            <p className="mt-2 text-muted">
              {status.claude ? "Claude rédige les réponses à partir des documents." : "Clé Claude absente : l'assistant cite les passages les plus pertinents."}{" "}
              {status.semantic_search ? "La recherche sémantique est active." : "La recherche se fait par mots-clés."}
            </p>
          )}
          <p className="mt-2 text-muted">Banque fictive : toutes les données sont des exemples. Ne saisissez aucune vraie donnée bancaire.</p>
        </div>
      </aside>
    </div>
  );
}
