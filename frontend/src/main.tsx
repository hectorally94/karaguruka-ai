import { StrictMode, useCallback, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, NavLink, Route, Routes, useNavigate } from "react-router-dom";
import { api, type Role } from "./api";
import "./index.css";
import AdminPage from "./pages/AdminPage";
import AgentPage from "./pages/AgentPage";
import AssistantPage from "./pages/AssistantPage";
import LoginPage from "./pages/LoginPage";

function Shell() {
  const [role, setRole] = useState<Role | undefined>(undefined);
  const navigate = useNavigate();

  const refresh = useCallback(async () => {
    await api<{ role: Role }>("/me").then((r) => setRole(r.role)).catch(() => setRole(null));
  }, []);
  useEffect(() => {
    void refresh();
  }, [refresh]);

  const logout = async () => {
    await api("/logout", { method: "POST" });
    setRole(null);
    navigate("/");
  };

  const link = ({ isActive }: { isActive: boolean }) =>
    `rounded-md px-3 py-1.5 text-sm font-medium ${isActive ? "bg-brand-soft text-ink" : "text-muted hover:text-ink"}`;

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <NavLink to="/" className="font-display text-lg font-bold">Karaguruka AI</NavLink>
          <nav className="flex flex-wrap items-center gap-1" aria-label="Navigation principale">
            <NavLink to="/" end className={link}>Assistant client</NavLink>
            <NavLink to="/agent" className={link}>Poste agent</NavLink>
            <NavLink to="/admin" className={link}>Administration</NavLink>
          </nav>
          <div className="ml-auto">
            {role && <button onClick={logout} className="text-sm text-muted hover:text-ink">Se déconnecter</button>}
          </div>
        </div>
      </header>
      <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col px-4 py-5">
        <Routes>
          <Route path="/" element={<AssistantPage />} />
          <Route path="/login" element={<LoginPage onLogin={refresh} />} />
          <Route path="/agent" element={role === undefined ? null : role ? <AgentPage /> : <Navigate to="/login?next=/agent" replace />} />
          <Route
            path="/admin"
            element={
              role === undefined ? null : role === "admin" ? <AdminPage /> : role === "agent" ? (
                <p className="text-muted">Cet espace est réservé aux administrateurs. Connectez-vous avec le mot de passe administrateur.</p>
              ) : <Navigate to="/login?next=/admin" replace />
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <Shell />
    </BrowserRouter>
  </StrictMode>,
);
