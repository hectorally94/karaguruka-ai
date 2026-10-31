import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, type AskResult, type DocumentRow, INTENT_LABELS, sourceLabel, type Stats } from "../api";

type Tab = "dashboard" | "documents" | "test" | "unanswered";
const TABS: [Tab, string][] = [["dashboard", "Tableau de bord"], ["documents", "Documents"], ["test", "Tester"], ["unanswered", "Questions sans réponse"]];
const message = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);

export default function AdminPage() {
  const [tab, setTab] = useState<Tab>("dashboard");
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end gap-x-6 gap-y-2">
        <h1 className="text-2xl font-bold">Administration</h1>
        <div role="tablist" className="flex flex-wrap gap-1">
          {TABS.map(([id, label]) => (
            <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)} className={`rounded-md px-3 py-1.5 text-sm font-medium ${tab === id ? "bg-brand text-brand-ink" : "text-muted hover:text-ink"}`}>
              {label}
            </button>
          ))}
        </div>
      </div>
      {tab === "dashboard" && <Dashboard />}
      {tab === "documents" && <Documents />}
      {tab === "test" && <TestArea />}
      {tab === "unanswered" && <Unanswered />}
    </div>
  );
}

function Tile({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="rounded-lg border border-line bg-surface p-4">
      <p className="text-sm text-muted">{label}</p>
      <p className="mt-1 font-display text-3xl font-bold tabular-nums">{value}</p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  );
}

function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const load = () => api<Stats>("/admin/stats").then(setStats).catch((e) => setError(message(e, "Les statistiques n'ont pas pu être chargées.")));
    load();
    const timer = setInterval(load, 10000);
    return () => clearInterval(timer);
  }, []);

  if (error) return <p role="alert" className="text-urgent">{error}</p>;
  if (!stats) return <p className="text-muted">Chargement…</p>;

  const share = stats.conversations ? Math.round((stats.handled_by_ai / stats.conversations) * 100) : 0;
  const hours = stats.minutes_saved / 60;
  const maxDay = Math.max(1, ...stats.by_day.map((d) => d.count));
  const maxIntent = Math.max(1, ...stats.by_intent.map((i) => i.count));

  return (
    <div className="flex flex-col gap-5">
      {stats.examples > 0 && (
        <p className="rounded-md bg-warn-soft px-3 py-2 text-sm text-warn">
          Ces chiffres incluent {stats.examples} conversation(s) d'exemple créée(s) pour la démonstration.
        </p>
      )}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Tile label="Conversations" value={stats.conversations} hint={`${stats.voice} en vocal`} />
        <Tile label="Traitées sans agent" value={`${share} %`} hint={`${stats.handled_by_ai} conversations sans dossier`} />
        <Tile label="Dossiers en cours" value={stats.tickets.open + stats.tickets.in_progress} hint={`${stats.tickets.urgent} urgent(s), ${stats.tickets.resolved} clôturé(s)`} />
        <Tile label="Temps agent estimé économisé" value={`${hours.toLocaleString("fr-FR", { maximumFractionDigits: 1 })} h`} hint={`Hypothèse : ${stats.handle_minutes} min par appel`} />
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <section className="rounded-lg border border-line bg-surface p-4">
          <h2 className="font-bold">Conversations des 7 derniers jours</h2>
          <div className="mt-4 flex h-44 items-end gap-2">
            {stats.by_day.map((d) => (
              <div key={d.day} className="flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-1" title={`${d.day} : ${d.count} conversation(s)`}>
                <span className="text-xs tabular-nums text-muted">{d.count > 0 ? d.count : ""}</span>
                <div className="w-full max-w-10 rounded-t bg-brand" style={{ height: `${(d.count / maxDay) * 75}%`, minHeight: d.count ? 4 : 1 }} />
                <span className="text-xs tabular-nums text-muted">{d.day.slice(8)}/{d.day.slice(5, 7)}</span>
              </div>
            ))}
          </div>
        </section>
        <section className="rounded-lg border border-line bg-surface p-4">
          <h2 className="font-bold">Types de demandes</h2>
          <ul className="mt-3 space-y-2">
            {stats.by_intent.map((i) => (
              <li key={i.intent} className="grid grid-cols-[minmax(0,10rem)_minmax(0,1fr)_2rem] items-center gap-2 text-sm" title={`${INTENT_LABELS[i.intent] ?? i.intent} : ${i.count}`}>
                <span className="truncate">{INTENT_LABELS[i.intent] ?? i.intent}</span>
                <span className="h-2 rounded-r bg-sunken"><span className="block h-2 rounded-r bg-brand" style={{ width: `${(i.count / maxIntent) * 100}%` }} /></span>
                <span className="text-right tabular-nums text-muted">{i.count}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>
      <p className="text-sm text-muted">
        {stats.documents.ready} document(s) actif(s) sur {stats.documents.total} · {stats.unanswered} question(s) sans réponse à examiner.
      </p>
    </div>
  );
}

const STATUS_LABEL = {
  processing: { text: "Traitement…", cls: "bg-warn-soft text-warn" },
  ready: { text: "Prêt", cls: "bg-good-soft text-good" },
  failed: { text: "Échec", cls: "bg-urgent-soft text-urgent" },
};

function Documents() {
  const [documents, setDocuments] = useState<DocumentRow[]>([]);
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [form, setForm] = useState({ title: "", category: "Général", audience: "public", effective_from: "", expires_at: "" });
  const fileInput = useRef<HTMLInputElement>(null);
  const replaceInput = useRef<HTMLInputElement>(null);
  const replaceTarget = useRef<string | null>(null);

  const load = useCallback(() => {
    api<DocumentRow[]>("/documents").then(setDocuments).catch((e) => setError(message(e, "La liste n'a pas pu être chargée.")));
  }, []);

  useEffect(load, [load]);

  const processing = documents.some((d) => d.status === "processing");
  useEffect(() => {
    if (!processing) return;
    const timer = setInterval(load, 2000);
    return () => clearInterval(timer);
  }, [processing, load]);

  const upload = async (event: FormEvent) => {
    event.preventDefault();
    const file = fileInput.current?.files?.[0];
    if (!file) return setError("Choisissez un fichier à envoyer.");
    const body = new FormData();
    body.set("file", file);
    body.set("title", form.title);
    body.set("category", form.category);
    body.set("audience", form.audience);
    if (form.effective_from) body.set("effective_from", form.effective_from);
    if (form.expires_at) body.set("expires_at", form.expires_at);
    setUploading(true);
    setError("");
    try {
      await api("/documents", { form: body });
      setForm({ ...form, title: "", effective_from: "", expires_at: "" });
      if (fileInput.current) fileInput.current.value = "";
      load();
    } catch (e) {
      setError(message(e, "L'envoi a échoué."));
    } finally {
      setUploading(false);
    }
  };

  const patch = async (id: string, json: object) => {
    setError("");
    try {
      await api(`/documents/${id}`, { method: "PATCH", json });
      load();
    } catch (e) {
      setError(message(e, "La modification a échoué."));
    }
  };

  const remove = async (id: string) => {
    setError("");
    setConfirmDelete(null);
    try {
      await api(`/documents/${id}`, { method: "DELETE" });
      load();
    } catch (e) {
      setError(message(e, "La suppression a échoué."));
    }
  };

  const replace = async (file: File | undefined) => {
    const id = replaceTarget.current;
    if (!file || !id) return;
    const body = new FormData();
    body.set("file", file);
    setError("");
    try {
      await api(`/documents/${id}/replace`, { form: body });
      load();
    } catch (e) {
      setError(message(e, "Le remplacement a échoué."));
    } finally {
      if (replaceInput.current) replaceInput.current.value = "";
    }
  };

  const field = "rounded-md border border-line bg-page px-3 py-2 text-sm";

  return (
    <div className="flex flex-col gap-5">
      <form onSubmit={(e) => void upload(e)} className="rounded-lg border border-line bg-surface p-4">
        <h2 className="font-bold">Ajouter un document</h2>
        <p className="text-sm text-muted">PDF (scanné ou non), Word, Excel, CSV, texte ou image, 25 Mo maximum. Ne déposez aucune donnée personnelle de client.</p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <label className="flex flex-col gap-1 text-sm">Fichier
            <input id="doc-file" ref={fileInput} type="file" accept=".pdf,.docx,.xlsx,.csv,.txt,.md,.png,.jpg,.jpeg" className={field} />
          </label>
          <label className="flex flex-col gap-1 text-sm">Titre (facultatif)
            <input id="doc-title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className={field} />
          </label>
          <label className="flex flex-col gap-1 text-sm">Catégorie
            <input id="doc-category" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} className={field} />
          </label>
          <label className="flex flex-col gap-1 text-sm">Visible par
            <select id="doc-audience" value={form.audience} onChange={(e) => setForm({ ...form, audience: e.target.value })} className={field}>
              <option value="public">Clients et agents</option>
              <option value="internal">Agents uniquement (interne)</option>
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm">En vigueur à partir du
            <input id="doc-from" type="date" value={form.effective_from} onChange={(e) => setForm({ ...form, effective_from: e.target.value })} className={field} />
          </label>
          <label className="flex flex-col gap-1 text-sm">Expire le
            <input id="doc-expires" type="date" value={form.expires_at} onChange={(e) => setForm({ ...form, expires_at: e.target.value })} className={field} />
          </label>
        </div>
        <button disabled={uploading} className="mt-3 rounded-md bg-brand px-4 py-2 font-medium text-brand-ink disabled:opacity-50">{uploading ? "Envoi…" : "Envoyer le document"}</button>
      </form>

      {error && <p role="alert" className="rounded-md bg-urgent-soft px-3 py-2 text-sm text-urgent">{error}</p>}

      <input ref={replaceInput} type="file" accept=".pdf,.docx,.xlsx,.csv,.txt,.md,.png,.jpg,.jpeg" hidden onChange={(e) => void replace(e.target.files?.[0])} />

      <div className="overflow-x-auto rounded-lg border border-line bg-surface">
        <table className="w-full min-w-[860px] text-left text-sm">
          <thead className="border-b border-line text-muted">
            <tr>
              <th className="px-4 py-2 font-medium">Document</th>
              <th className="px-4 py-2 font-medium">État</th>
              <th className="px-4 py-2 font-medium">Visible par</th>
              <th className="px-4 py-2 font-medium">Expire le</th>
              <th className="px-4 py-2 font-medium">Actif</th>
              <th className="px-4 py-2 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {documents.length === 0 && <tr><td colSpan={6} className="px-4 py-6 text-muted">Aucun document. Ajoutez le premier pour que l'assistant puisse répondre.</td></tr>}
            {documents.map((d) => (
              <tr key={d.id} className="align-top">
                <td className="px-4 py-3">
                  <p className="font-medium">{d.title}</p>
                  <p className="text-xs text-muted">{d.category} · {d.filename} · v{d.version}{d.status === "ready" ? ` · ${d.chunk_count} passage(s)` : ""}{d.used_ocr ? " · OCR" : ""}</p>
                  {d.error && <p className="mt-1 text-xs text-urgent">{d.error}</p>}
                  {d.status === "ready" && d.embedded_count !== undefined && d.embedded_count < d.chunk_count && (
                    <p className="mt-1 text-xs text-warn">Recherche par mots-clés seulement pour une partie du document. Remplacez le fichier pour relancer l'indexation.</p>
                  )}
                </td>
                <td className="px-4 py-3"><span className={`rounded px-1.5 py-0.5 text-xs font-medium ${STATUS_LABEL[d.status].cls}`}>{STATUS_LABEL[d.status].text}</span></td>
                <td className="px-4 py-3">
                  <select aria-label={`Visibilité de ${d.title}`} value={d.audience} onChange={(e) => void patch(d.id, { audience: e.target.value })} className="rounded border border-line bg-page px-2 py-1">
                    <option value="public">Clients et agents</option>
                    <option value="internal">Agents uniquement</option>
                  </select>
                </td>
                <td className="px-4 py-3">
                  <input aria-label={`Expiration de ${d.title}`} type="date" value={d.expires_at ?? ""} onChange={(e) => void patch(d.id, { expires_at: e.target.value || null })} className="rounded border border-line bg-page px-2 py-1" />
                </td>
                <td className="px-4 py-3">
                  <input aria-label={`Activer ${d.title}`} type="checkbox" checked={d.active} onChange={(e) => void patch(d.id, { active: e.target.checked })} className="size-4" />
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-3">
                    <button onClick={() => { replaceTarget.current = d.id; replaceInput.current?.click(); }} className="text-brand underline">Remplacer</button>
                    <a href={`/api/documents/${d.id}/download`} className="text-brand underline">Télécharger</a>
                    {confirmDelete === d.id ? (
                      <>
                        <button onClick={() => void remove(d.id)} className="font-medium text-urgent underline">Confirmer</button>
                        <button onClick={() => setConfirmDelete(null)} className="text-muted underline">Annuler</button>
                      </>
                    ) : (
                      <button onClick={() => setConfirmDelete(d.id)} className="text-urgent underline">Supprimer</button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TestArea() {
  const [question, setQuestion] = useState("Quels documents faut-il pour ouvrir un compte ?");
  const [audience, setAudience] = useState("public");
  const [result, setResult] = useState<AskResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const ask = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      setResult(await api<AskResult>("/admin/ask", { json: { question, audience } }));
    } catch (e) {
      setError(message(e, "Le test a échoué."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <form onSubmit={(e) => void ask(e)} className="rounded-lg border border-line bg-surface p-4">
        <h2 className="font-bold">Tester une question</h2>
        <p className="text-sm text-muted">Vérifiez la réponse et ses sources. Ce test n'apparaît pas dans les statistiques.</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <label htmlFor="test-question" className="sr-only">Question</label>
          <input id="test-question" value={question} onChange={(e) => setQuestion(e.target.value)} className="min-w-0 flex-1 basis-64 rounded-md border border-line bg-page px-3 py-2" />
          <label htmlFor="test-audience" className="sr-only">Répondre comme pour</label>
          <select id="test-audience" value={audience} onChange={(e) => setAudience(e.target.value)} className="rounded-md border border-line bg-page px-3 py-2">
            <option value="public">Vue client</option>
            <option value="internal">Vue agent</option>
          </select>
          <button disabled={busy || !question.trim()} className="rounded-md bg-brand px-4 py-2 font-medium text-brand-ink disabled:opacity-50">{busy ? "Recherche…" : "Tester"}</button>
        </div>
      </form>
      {error && <p role="alert" className="rounded-md bg-urgent-soft px-3 py-2 text-sm text-urgent">{error}</p>}
      {result && (
        <>
          <section className="rounded-lg border border-line bg-surface p-4">
            <h3 className="font-bold">{result.found ? "Réponse" : result.route === "not_found" ? "Pas de réponse trouvée" : "Orientation vers un parcours guidé"}</h3>
            <p className="mt-2 whitespace-pre-line">{result.found ? result.answer : result.route === "not_found" ? "L'assistant proposerait un conseiller et ajouterait la question à la liste à examiner." : `Parcours : ${result.route}`}</p>
            {result.sources.length > 0 && <p className="mt-2 text-sm text-muted">Source : {result.sources.map(sourceLabel).join(" ; ")}</p>}
            <p className="mt-2 text-xs text-muted">{result.mode === "claude" ? "Rédigée par Claude" : "Extrait direct du document (sans Claude)"}</p>
          </section>
          <section className="rounded-lg border border-line bg-surface p-4">
            <h3 className="font-bold">Passages retrouvés</h3>
            {result.excerpts.length === 0 && <p className="mt-2 text-sm text-muted">Aucun passage.</p>}
            <ul className="mt-2 divide-y divide-line">
              {result.excerpts.map((x, i) => (
                <li key={i} className="py-2 text-sm">
                  <p className="font-medium">{x.title}{x.page ? `, page ${x.page}` : ""} <span className="font-mono text-xs font-normal text-muted">termes trouvés {Math.round(x.coverage * 100)} %</span></p>
                  <p className="text-muted">{x.content}</p>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </div>
  );
}

function Unanswered() {
  const [rows, setRows] = useState<{ id: number; question: string; created_at: string }[]>([]);
  const [error, setError] = useState("");
  const load = useCallback(() => {
    api<typeof rows>("/admin/unanswered").then(setRows).catch((e) => setError(message(e, "La liste n'a pas pu être chargée.")));
  }, []);
  useEffect(load, [load]);

  const dismiss = async (id: number) => {
    try {
      await api(`/admin/unanswered/${id}/dismiss`, { method: "POST" });
      load();
    } catch (e) {
      setError(message(e, "L'action a échoué."));
    }
  };

  return (
    <section className="rounded-lg border border-line bg-surface p-4">
      <h2 className="font-bold">Questions sans réponse</h2>
      <p className="text-sm text-muted">Les documents n'ont pas permis d'y répondre. Ajoutez le document manquant, puis retirez la question de la liste.</p>
      {error && <p role="alert" className="mt-2 text-sm text-urgent">{error}</p>}
      <ul className="mt-3 divide-y divide-line">
        {rows.length === 0 && <li className="py-3 text-sm text-muted">Aucune question à examiner.</li>}
        {rows.map((row) => (
          <li key={row.id} className="flex items-center gap-3 py-2 text-sm">
            <span className="min-w-0 flex-1">{row.question}</span>
            <span className="text-xs text-muted">{new Date(row.created_at).toLocaleDateString("fr-FR")}</span>
            <button onClick={() => void dismiss(row.id)} className="text-brand underline">Retirer</button>
          </li>
        ))}
      </ul>
    </section>
  );
}
