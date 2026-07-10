import React from "react";
import Head from "next/head";
import Link from "next/link";
import PublicHeader from "../components/PublicHeader";
import Footer from "../components/Footer";
import ProductPreview, { AnalyticsPreview } from "../components/ProductPreview";
import PlatformTabs from "../components/PlatformTabs";

const stack = [
  { n:"01", title:"FacilityGraph Core", copy:"A connected operational graph for assets, rooms, incidents, dependencies, and lifecycle history.", items:["Asset inventory","Dependency mapping","Room context","Incident history","Replacement tracking"], className:"core" },
  { n:"02", title:"AI Maintenance Copilot", copy:"A grounded assistant that combines graph context with manuals and historical incidents.", items:["Hybrid retrieval","Manual search","Evidence citations","Confidence scoring","xAI/Grok generation"], className:"copilot" },
];
const features = [
  ["⌘","Asset Intelligence","Connect device identity, room placement, dependencies, and operational history in Neo4j."],
  ["✦","Grounded AI Answers","Generate maintenance guidance from retrieved graph facts and document evidence."],
  ["!","Incident Context","Search problems, previous resolutions, technicians, and device-specific history."],
  ["◎","Explainable Retrieval","Inspect citations, source types, route selection, and confidence for every answer."],
  ["♙","Role-aware Access","Demonstrate operator, technician, and admin permissions through seeded local identities."],
  ["↺","Historical Replacement Tracking","Retain lifecycle context and relationship continuity when an admin replaces a device."],
];

export default function HomePage() {
  return <><Head><title>FacilityGraph AI · Connected Maintenance Intelligence</title></Head><PublicHeader /><main>
    <section className="hero"><div className="hero-grid" /><div className="wrap hero-inner"><div className="hero-badge"><i>✦</i> AI Maintenance Intelligence Platform <span>LOCAL-FIRST</span></div><h1>Connected Maintenance Intelligence.<br /><span>Powered by <em>Graph + RAG.</em></span></h1><p>FacilityGraph AI connects devices, rooms, incidents, manuals, and maintenance history into one explainable AI workspace.</p><div className="hero-actions"><Link href="/login" className="button button-accent">Open Demo Workspace <span>↗</span></Link><Link href="#platform" className="button button-light">Explore the Platform <span>↓</span></Link></div><div className="trust-row">{["Neo4j Knowledge Graph","Weaviate Retrieval","Evidence-backed answers","Role-aware workflows"].map((item)=><span key={item}><i>✓</i>{item}</span>)}</div><ProductPreview /></div></section>

    <section className="section stack-section" id="platform"><div className="wrap"><div className="section-heading centered"><span className="kicker">PLATFORM COMPONENTS</span><h2>The Complete Stack for<br />AI Facility Operations</h2><p>Purpose-built layers for connecting operational knowledge with explainable AI retrieval.</p></div><div className="stack-grid">{stack.map((card)=><article key={card.title} className={`stack-card ${card.className}`}><div className="stack-number">{card.n}</div><span className="stack-icon">{card.className==="core"?"⌘":"✦"}</span><h3>{card.title}</h3><p>{card.copy}</p><div>{card.items.map((item)=><span key={item}><i>✓</i>{item}</span>)}</div><div className="stack-art" aria-hidden="true">{card.className==="core"?<><i/><i/><i/><i/><b/></>:<><span>GRAPH</span><span>RAG</span><b>✦</b></>}</div></article>)}</div></div></section>

    <section className="section tab-section" id="use-cases"><div className="wrap"><div className="section-heading split"><div><span className="kicker">ONE CONNECTED PLATFORM</span><h2>Operational intelligence,<br />from every angle.</h2></div><p>Move between connected asset context, retrieved maintenance knowledge, and incident history without losing the evidence behind the answer.</p></div><PlatformTabs /></div></section>

    <section className="section connected-section" id="how-it-works"><div className="wrap connected-grid"><div className="connection-diagram"><div className="connection-line horizontal"/><div className="connection-line vertical"/><div className="connection-node assets"><span>▱</span><b>Assets</b></div><div className="connection-node incidents"><span>!</span><b>Incidents</b></div><div className="connection-node manuals"><span>≡</span><b>Manuals</b></div><div className="connection-node relations"><span>⌘</span><b>Relationships</b></div><div className="connection-core"><i>✦</i><b>Graph + RAG</b><small>ROUTED INTELLIGENCE</small></div></div><div className="connected-copy"><span className="kicker">CONNECTED INTELLIGENCE</span><h2>Maintenance decisions improve when every source is connected.</h2><p>FacilityGraph AI routes each question to the evidence source best suited to answer it.</p><ul><li><i>01</i><span><b>Graph relationships</b> provide operational context.</span></li><li><i>02</i><span><b>Manuals</b> provide technical procedures.</span></li><li><i>03</i><span><b>Incidents</b> provide historical evidence.</span></li><li><i>04</i><span><b>AI</b> combines them into explainable answers.</span></li></ul></div></div></section>

    <section className="section feature-section"><div className="wrap"><div className="section-heading centered"><span className="kicker">BUILT FOR EXPLAINABILITY</span><h2>Context for every maintenance question.</h2><p>Focused capabilities that reflect the system’s real graph, retrieval, and lifecycle workflows.</p></div><div className="feature-grid">{features.map(([icon,title,copy],index)=><article key={title}><span className="feature-icon">{icon}</span><small>0{index+1}</small><h3>{title}</h3><p>{copy}</p><i className="feature-arrow">↗</i></article>)}</div></div></section>

    <section className="section analytics-section" id="architecture"><div className="wrap"><div className="section-heading split"><div><span className="kicker">OPERATIONAL VISIBILITY</span><h2>See the context behind<br />every maintenance decision.</h2></div><p>Use real device and incident endpoints for workspace views, then inspect graph and evidence context as questions move through retrieval.</p></div><AnalyticsPreview /><div className="benefit-row">{[["01","Find the affected asset context before troubleshooting."],["02","Retrieve graph and manual evidence in one workflow."],["03","Understand why each answer was produced."]].map(([n,text])=><div key={n}><i>{n}</i><p>{text}</p></div>)}</div></div></section>

    <section className="dark-section"><div className="dark-grid"/><div className="wrap"><div className="dark-head"><div><span className="kicker light">FACILITYGRAPH AI</span><h2>Intelligence you can<br />inspect and explain.</h2></div><Link href="/login" className="button button-white">Open Demo Workspace <span>↗</span></Link></div><div className="capability-grid">{[["GRAPH + RAG","Hybrid operational retrieval"],["CITED","Evidence-linked answers"],["ROLE-AWARE","Operator, technician, and admin workflows"],["LOCAL-FIRST","Dockerized application stack"]].map(([title,copy],i)=><article key={title}><small>0{i+1}</small><i>{["⌘","✓","♙","◇"][i]}</i><h3>{title}</h3><p>{copy}</p></article>)}</div></div></section>
  </main><Footer /></>;
}
