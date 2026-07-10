import React, { useState } from "react";
import Link from "next/link";
import { LogoMark } from "./Brand";

const links = [
  ["Platform", "#platform"], ["How It Works", "#how-it-works"], ["Use Cases", "#use-cases"],
  ["Architecture", "#architecture"], ["Documentation", "/app/settings"],
];

export default function PublicHeader() {
  const [open, setOpen] = useState(false);
  return (
    <header className="public-header">
      <div className="public-nav wrap">
        <LogoMark />
        <button className="mobile-menu" onClick={() => setOpen(!open)} aria-expanded={open} aria-label="Toggle navigation">
          <span /><span /><span />
        </button>
        <nav className={open ? "nav-links open" : "nav-links"} aria-label="Primary navigation">
          {links.map(([label, href]) => <Link key={label} href={href} onClick={() => setOpen(false)}>{label}</Link>)}
        </nav>
        <div className="nav-actions">
          <Link href="/login" className="text-link">Sign In</Link>
          <Link href="/register" className="button button-ghost">Create Account</Link>
          <Link href="/login" className="button button-dark">Open Workspace <span aria-hidden="true">↗</span></Link>
        </div>
      </div>
    </header>
  );
}
