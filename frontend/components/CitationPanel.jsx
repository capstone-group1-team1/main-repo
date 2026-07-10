import React from "react";

export default function CitationPanel({ citations = [], highlighted }) {
  return (
    <section className="evidence-panel panel">
      <div className="panel-heading"><div><span className="kicker">RETRIEVED EVIDENCE</span><h2>Sources</h2></div><span className="count-pill">{citations.length}</span></div>
      {!citations.length ? <div className="empty-compact"><span>◎</span><p>Evidence sources will appear here after an answer.</p></div> : citations.map((citation) => (
        <article key={citation.marker} id={`cite-${citation.marker}`} className={`citation ${highlighted === citation.marker ? "highlight" : ""}`}>
          <div className="citation-head"><span className="citation-number">[{citation.marker}]</span><span className={`source-type ${citation.source_type}`}>{citation.source_type}</span></div>
          <b>{citation.source_id}{citation.page_number ? ` · page ${citation.page_number}` : ""}</b>
          <p>{citation.snippet}</p>
        </article>
      ))}
    </section>
  );
}
