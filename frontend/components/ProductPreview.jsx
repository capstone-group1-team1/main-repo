import React from "react";

export function MiniGraph() {
  return <div className="mini-graph" aria-label="CP4 dependency graph"><span className="graph-wire w1" /><span className="graph-wire w2" /><span className="graph-wire w3" /><div className="g-node cp4"><i />CP4<small>CONTROL</small></div><div className="g-node display"><i />Display</div><div className="g-node audio"><i />Audio Processor</div><div className="g-node touch"><i />Touch Panel</div></div>;
}

export default function ProductPreview() {
  const menu = ["Overview", "AI Assistant", "Devices", "Incidents", "Knowledge Graph", "Settings"];
  return (
    <div className="browser-preview" aria-label="FacilityGraph AI application preview">
      <div className="browser-bar"><span /><span /><span /><div>workspace.facilitygraph.ai</div><i>LIVE DEMO</i></div>
      <div className="preview-app">
        <aside><div className="preview-logo"><b>F</b> FacilityGraph</div>{menu.map((item, index) => <span key={item} className={index === 1 ? "active" : ""}><i>{["⌂","✦","▱","!","⌘","⚙"][index]}</i>{item}</span>)}</aside>
        <main>
          <header><div><small>OPERATIONS WORKSPACE</small><b>AI Maintenance Assistant</b></div><span><i /> API ONLINE</span><em>OA</em></header>
          <div className="preview-body">
            <div className="preview-metrics">{[["TOTAL DEVICES","10","Asset inventory"],["OPEN INCIDENTS","—","Live graph query"],["GRAPH RELATIONSHIPS","24","Seed relationships"],["EVIDENCE SOURCES","2","This answer"]].map(([label,value,note]) => <div key={label}><small>{label}</small><b>{value}</b><span>{note}</span></div>)}</div>
            <div className="preview-chat-area">
              <section className="preview-chat"><div className="preview-user"><small>YOU</small>What devices depend on the Crestron CP4?</div><div className="preview-answer"><div><span className="spark">✦</span><small>FACILITYGRAPH AI</small><em>Route: Graph</em></div><p>The CP4 control processor directly controls the Samsung display, Cisco Codec EQ, and AirMedia receiver. The TST-1080 touch panel uses the CP4 as its control endpoint. <b>[1]</b> <b>[2]</b></p><div className="answer-signals"><span>● HIGH CONFIDENCE · 0.91</span><span>4 graph facts</span></div></div><div className="preview-evidence"><strong>RETRIEVED EVIDENCE</strong><div><b>[1] NEO4J</b><p>CP4-001 —CONTROLS→ DSP-001</p></div><div><b>[2] WEAVIATE</b><p>CP4 control and touch-panel context</p></div></div></section>
              <section className="preview-graph-card"><div><small>DIRECT RELATIONSHIPS</small><b>CP4 neighborhood</b></div><MiniGraph /><footer><span><i className="purple" /> Depends on</span><span><i className="cyan" /> Controls</span></footer></section>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

export function AnalyticsPreview() {
  return <div className="analytics-window">
    <div className="analytics-head"><div><small>OPERATIONS OVERVIEW</small><b>Facility intelligence</b></div><span>LAST DATA REFRESH · LIVE</span></div>
    <div className="analytics-metrics"><div><small>DEVICE HEALTH</small><b>10</b><span><i /> Active inventory records</span></div><div><small>INCIDENT STATUS</small><b>16</b><span>Historical seed records</span></div><div><small>GRAPH CONNECTIONS</small><b>24</b><span>Seed relationships</span></div></div>
    <div className="analytics-grid"><section><div className="chart-title"><b>Graph dependency visualization</b><span>Meeting Room</span></div><MiniGraph /></section><section><div className="chart-title"><b>Evidence source distribution</b><span>Illustrative preview</span></div><div className="source-bars"><div><label>Graph facts <b>54%</b></label><span><i style={{width:"54%"}} /></span></div><div><label>Manual chunks <b>29%</b></label><span><i style={{width:"29%"}} /></span></div><div><label>Incident history <b>17%</b></label><span><i style={{width:"17%"}} /></span></div></div></section><section className="recent-queries"><div className="chart-title"><b>Recent maintenance questions</b><span>Demo view</span></div>{["What depends on the CP4?","Why is the display showing no signal?","Find similar AirMedia incidents"].map((q,i)=><div key={q}><i>0{i+1}</i><span>{q}<small>{["GRAPH","HYBRID","RAG"][i]} ROUTE</small></span><b>→</b></div>)}</section></div>
  </div>;
}
