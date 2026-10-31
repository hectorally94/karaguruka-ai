import { type FormEvent, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api";

export default function LoginPage({ onLogin }: { onLogin: () => Promise<void> }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [params] = useSearchParams();
  const navigate = useNavigate();

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      const { role } = await api<{ role: string }>("/login", { json: { password } });
      // The protected pages read the role, so it has to be current before leaving this page.
      await onLogin();
      const next = params.get("next");
      navigate(next === "/admin" || next === "/agent" ? next : role === "admin" ? "/admin" : "/agent");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "La connexion a échoué.");
    }
  };

  return (
    <form onSubmit={submit} className="mx-auto mt-12 flex w-full max-w-sm flex-col gap-3 rounded-lg border border-line bg-surface p-6">
      <h1 className="text-xl font-bold">Espace du personnel</h1>
      <label htmlFor="password" className="text-sm text-muted">Mot de passe agent ou administrateur</label>
      <input id="password" type="password" autoFocus value={password} onChange={(e) => setPassword(e.target.value)} className="rounded-md border border-line bg-page px-3 py-2" />
      {error && <p role="alert" className="text-sm text-urgent">{error}</p>}
      <button className="rounded-md bg-brand px-4 py-2 font-medium text-brand-ink">Se connecter</button>
    </form>
  );
}
