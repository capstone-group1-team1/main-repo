import React from "react";
import { LogoMark } from "./Brand";

export default function AuthVisual() {
  return (
    <div className="auth-visual">
      <LogoMark />
      <div className="auth-copy"><span className="kicker light">CONNECTED OPERATIONS</span><h1>One workspace for assets, incidents, manuals, and maintenance intelligence.</h1><p>Trace the evidence. Understand the relationships. Make maintenance decisions with context.</p></div>
      <svg className="auth-graph" viewBox="0 0 620 360" role="img" aria-label="Connected asset, incident, manual, and room graph">
        <defs><linearGradient id="line" x1="0" x2="1"><stop stopColor="#70e5ff" /><stop offset="1" stopColor="#9977ff" /></linearGradient></defs>
        <g className="graph-lines"><path d="M95 80L276 170L475 78M276 170L500 280M276 170L88 290M475 78L500 280M95 80L88 290" /></g>
        <g className="graph-node node-main"><circle cx="276" cy="170" r="62" /><text x="276" y="163">GRAPH + RAG</text><text className="small" x="276" y="186">INTELLIGENCE</text></g>
        <g className="graph-node"><circle cx="95" cy="80" r="44" /><text x="95" y="85">ASSETS</text></g>
        <g className="graph-node"><circle cx="475" cy="78" r="44" /><text x="475" y="83">ROOMS</text></g>
        <g className="graph-node"><circle cx="500" cy="280" r="52" /><text x="500" y="285">INCIDENTS</text></g>
        <g className="graph-node"><circle cx="88" cy="290" r="48" /><text x="88" y="295">MANUALS</text></g>
      </svg>
      <div className="auth-trust"><span>NEO4J</span><span>WEAVIATE</span><span>FASTAPI</span><span>XAI / GROK</span></div>
    </div>
  );
}
