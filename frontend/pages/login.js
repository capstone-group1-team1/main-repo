import React, { useState } from "react";
import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";
import AuthVisual from "../components/AuthVisual";
import { DEMO_ROLES, saveSession } from "../lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [role, setRole] = useState("operator");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  function submit(event) {
    event.preventDefault();
    saveSession(role);
    const destination = typeof router.query.next === "string" && router.query.next.startsWith("/app") ? router.query.next : "/app";
    router.push(destination);
  }

  return (
    <><Head><title>Sign In · FacilityGraph AI</title></Head><main className="auth-page">
      <AuthVisual />
      <section className="auth-form-wrap"><div className="auth-form-card"><span className="kicker">LOCAL DEMO WORKSPACE</span><h2>Welcome back</h2><p className="form-intro">Choose a demo role to explore role-aware facility intelligence.</p>
        <form onSubmit={submit}>
          <label htmlFor="email">Email</label><input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@organization.com" autoComplete="email" required />
          <label htmlFor="password">Password</label><input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Enter any demo password" autoComplete="current-password" required />
          <fieldset><legend>Role / demo account</legend><div className="role-selector">{Object.entries(DEMO_ROLES).map(([key, user]) => <label key={key} className={role === key ? "selected" : ""}><input type="radio" name="role" value={key} checked={role === key} onChange={() => setRole(key)} /><span><i>{user.label.charAt(0)}</i><b>{user.label}</b><small>{user.id}</small></span></label>)}</div></fieldset>
          <button className="button button-accent button-full" type="submit">Sign In to Workspace <span>→</span></button>
        </form>
        <div className="demo-note"><span>i</span><p><b>Local demo authentication.</b> Not production security. Your password is not stored or sent to the backend.</p></div>
        <p className="auth-switch">New to the demo? <Link href="/register">Create Account</Link></p>
      </div></section>
    </main></>
  );
}
