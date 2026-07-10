import React from "react";

export default function ConfidenceBadge({ confidence = {}, citationCount = 0 }) {
  let final = Number(confidence.final || 0);
  if (citationCount === 0) final = Math.min(final, 0.25);
  const level = final >= 0.75 ? "high" : final < 0.4 ? "low" : "medium";
  const label = `${level.charAt(0).toUpperCase()}${level.slice(1)} confidence`;
  const sig = (value) => value === null || value === undefined ? "—" : Number(value).toFixed(2);
  return (
    <div className="confidence-block">
      <div className="confidence-row">
        <span className={`confidence-pill ${level}`}><i />{label} <b>{final.toFixed(2)}</b></span>
        <span className="signal-list">Retrieval {sig(confidence.retrieval)} · Graph {sig(confidence.graph)}</span>
      </div>
      {final < 0.4 && <div className="alert warning">Low confidence — technician review is recommended before acting on this answer.</div>}
    </div>
  );
}
