import React, { useState } from "react";
import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";
import AuthVisual from "../components/AuthVisual";
import { saveSession } from "../lib/auth";

export default function RegisterPage() {
  const router = useRouter();
  const [form, setForm] = useState({ fullName: "", email: "", organization: "", password: "", role: "operator" });
  const update = (key) => (event) => setForm({ ...form, [key]: event.target.value });
  function submit(event) {
    event.preventDefault();
    saveSession(form.role, form);
    router.push("/app");
  }
  return (
    <><Head><title>Create Demo Profile · FacilityGraph AI</title></Head><main className="auth-page">
      <AuthVisual />
      <section className="auth-form-wrap"><div className="auth-form-card register-card"><span className="kicker">LOCAL DEMO WORKSPACE</span><h2>Create Demo Workspace Profile</h2><p className="form-intro">Create a local profile mapped to one of the seeded backend roles.</p>
        <form onSubmit={submit} className="form-grid">
          <div><label htmlFor="fullName">Full name</label><input id="fullName" value={form.fullName} onChange={update("fullName")} placeholder="Your name" required /></div>
          <div><label htmlFor="regEmail">Email</label><input id="regEmail" type="email" value={form.email} onChange={update("email")} placeholder="you@organization.com" required /></div>
          <div><label htmlFor="organization">Organization</label><input id="organization" value={form.organization} onChange={update("organization")} placeholder="Facility Operations" required /></div>
          <div><label htmlFor="regPassword">Password</label><input id="regPassword" type="password" value={form.password} onChange={update("password")} placeholder="Not stored" required /></div>
          <div className="form-span"><label htmlFor="role">Requested role</label><select id="role" value={form.role} onChange={update("role")}><option value="operator">Operator — view and ask</option><option value="technician">Technician — view, ask, and log incidents</option><option value="admin">Admin — full demo permissions</option></select></div>
          <button className="button button-accent button-full form-span" type="submit">Create Demo Profile <span>→</span></button>
        </form>
        <div className="demo-note"><span>i</span><p>This profile stays in this browser. It is not persisted to a production backend, and the password is never stored.</p></div>
        <p className="auth-switch">Already have a demo profile? <Link href="/login">Sign In</Link></p>
      </div></section>
    </main></>
  );
}
