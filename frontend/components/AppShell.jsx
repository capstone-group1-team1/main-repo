import React, { createContext, useContext, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import { LogoMark } from "./Brand";
import { api } from "../lib/api";
import { clearSession, getSession } from "../lib/auth";

const WorkspaceContext = createContext(null);

const navigation = [
  ["/app", "Overview", "⌂"],
  ["/app/assistant", "AI Assistant", "✦"],
  ["/app/devices", "Devices", "▱"],
  ["/app/incidents", "Incidents", "!"],
  ["/app/graph", "Knowledge Graph", "⌘"],
  ["/app/settings", "Settings", "⚙"],
];

export function useWorkspace() {
  return useContext(WorkspaceContext);
}

export default function AppShell({ children, title, eyebrow = "OPERATIONS WORKSPACE" }) {
  const router = useRouter();
  const [session, setSession] = useState(null);
  const [ready, setReady] = useState(false);
  const [apiStatus, setApiStatus] = useState("checking");
  const [storeStatus, setStoreStatus] = useState("checking");
  const [toast, setToast] = useState(null);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const current = getSession();
    if (!current) router.replace(`/login?next=${encodeURIComponent(router.asPath)}`);
    else setSession(current);
    setReady(true);
  }, []);

  useEffect(() => {
    api.health().then(() => setApiStatus("online")).catch(() => setApiStatus("offline"));
    api.readiness().then(() => setStoreStatus("ready")).catch(() => setStoreStatus("check"));
  }, []);

  function showError(message) {
    setToast(message || "Something went wrong. Please try again.");
    window.setTimeout(() => setToast(null), 5200);
  }

  function logout() {
    clearSession();
    router.push("/login");
  }

  if (!ready || !session) return <div className="page-loader"><span className="spinner" />Loading workspace…</div>;

  return (
    <WorkspaceContext.Provider value={{ session, api, apiStatus, showError }}>
      <div className="workspace-shell">
        <aside className={menuOpen ? "app-sidebar open" : "app-sidebar"}>
          <div className="sidebar-brand"><LogoMark /></div>
          <div className="workspace-label"><span>Workspace</span><strong>{session.profile?.organization || "Facility Operations"}</strong></div>
          <nav aria-label="Workspace navigation">
            {navigation.map(([href, label, icon]) => {
              const active = href === "/app" ? router.pathname === href : router.pathname.startsWith(href);
              return <Link key={href} href={href} className={active ? "active" : ""} onClick={() => setMenuOpen(false)}><i>{icon}</i>{label}</Link>;
            })}
          </nav>
          <div className="sidebar-system">
            <div className="system-pulse"><span /><div><b>Graph + RAG</b><small>Operational pipeline</small></div></div>
            <div className="system-row"><span>Neo4j</span><b>{storeStatus}</b></div>
            <div className="system-row"><span>Weaviate</span><b>{storeStatus}</b></div>
          </div>
        </aside>

        <div className="workspace-main">
          <header className="app-topbar">
            <button className="sidebar-toggle" aria-label="Toggle workspace menu" onClick={() => setMenuOpen(!menuOpen)}>☰</button>
            <div><span className="app-eyebrow">{eyebrow}</span><h1>{title}</h1></div>
            <div className="topbar-actions">
              <span className={`api-state ${apiStatus}`}><i /> API {apiStatus}</span>
              <span className={`role-pill role-${session.role}`}>{session.label}</span>
              <details className="user-menu">
                <summary aria-label="Open user menu"><span>{(session.profile?.fullName || session.name).charAt(0)}</span><div><b>{session.profile?.fullName || session.name}</b><small>{session.userId}</small></div></summary>
                <div><button onClick={logout}>Log out</button></div>
              </details>
            </div>
          </header>
          <main className="workspace-content">{children}</main>
        </div>
        {toast && <div className="toast" role="alert">{toast}</div>}
      </div>
    </WorkspaceContext.Provider>
  );
}
