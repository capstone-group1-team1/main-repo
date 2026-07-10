import React from "react";
import Link from "next/link";
import { LogoMark } from "./Brand";

const groups = {
  Platform: [["AI Assistant", "/app/assistant"], ["Knowledge Graph", "/app/graph"], ["Device Explorer", "/app/devices"], ["Incident Intelligence", "/app/incidents"]],
  Technology: [["Neo4j", "#architecture"], ["Weaviate", "#architecture"], ["FastAPI", "#architecture"], ["Next.js", "#architecture"], ["xAI / Grok", "#architecture"]],
  Resources: [["Documentation", "/app/settings"], ["Architecture", "#architecture"], ["Setup Guide", "/app/settings"], ["API Health", "/app/settings"], ["Evaluation", "/app/settings"]],
  Project: [["About", "#platform"], ["GitHub", "/app/settings"], ["Team", "/app/settings"], ["Contact", "/app/settings"]],
};

export default function Footer() {
  return (
    <footer className="site-footer">
      <div className="wrap footer-grid">
        <div className="footer-brand"><LogoMark /><p>Explainable maintenance intelligence built from the operational context you already have.</p></div>
        {Object.entries(groups).map(([title, links]) => (
          <div key={title}><h3>{title}</h3>{links.map(([label, href]) => <Link key={label} href={href}>{label}</Link>)}</div>
        ))}
      </div>
      <div className="wrap footer-bottom">© 2026 FacilityGraph AI. Explainable intelligence for facility maintenance.</div>
    </footer>
  );
}
