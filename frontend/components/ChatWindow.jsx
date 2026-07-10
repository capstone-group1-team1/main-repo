import React, { useState } from "react";
import ConfidenceBadge from "./ConfidenceBadge";
import CitationPanel from "./CitationPanel";

function renderAnswer(text = "", unsourced = [], onMarkerClick) {
  return text.split(/(\[\d+\])/g).map((part, index) => {
    const marker = part.match(/^\[(\d+)\]$/);
    if (marker) return <button key={index} className="cite-marker" onClick={() => onMarkerClick(Number(marker[1]))}>[{marker[1]}]</button>;
    const lacksSource = unsourced.some((item) => item.length > 8 && part.includes(item.slice(0, 20)));
    return lacksSource ? <span key={index} className="unsourced" title="No retrieved source supports this span">{part}</span> : <span key={index}>{part}</span>;
  });
}

function safeError(error) {
  const message = error?.reason || error?.message || "The request could not be completed.";
  const providerProblem = /LLM|xAI|provider|API key|authentication|unauthorized/i.test(message);
  if (providerProblem) return { type: "provider", message: "AI provider is not configured correctly. Verify XAI_API_KEY and restart the API service." };
  if (error?.status === 0 || /offline|reach the backend/i.test(message)) return { type: "offline", message: "The backend is offline. Start the API service, then try again." };
  return { type: "request", message };
}

export default function ChatWindow({ ask }) {
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState([]);
  const [loading, setLoading] = useState(false);
  const [highlight, setHighlight] = useState(null);
  const suggestions = ["What devices depend on the CP4?", "Show incidents for the meeting room display", "How do I troubleshoot an offline AirMedia receiver?"];

  async function submit(input = question) {
    const clean = input.trim();
    if (!clean || loading) return;
    setQuestion(""); setLoading(true);
    try {
      const response = await ask(clean);
      setTurns((current) => [...current, { question: clean, response }]);
      try {
        const existing = JSON.parse(window.localStorage.getItem("facilitygraph.questions") || "[]");
        window.localStorage.setItem("facilitygraph.questions", JSON.stringify([{ question: clean, route: response.route, at: new Date().toISOString() }, ...existing].slice(0, 8)));
      } catch { /* Recent-question history is a local convenience only. */ }
    }
    catch (error) { setTurns((current) => [...current, { question: clean, error: safeError(error) }]); }
    finally { setLoading(false); }
  }

  function onMarkerClick(number) {
    setHighlight(number);
    document.getElementById(`cite-${number}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  const latest = [...turns].reverse().find((turn) => turn.response)?.response;
  return (
    <div className="assistant-grid">
      <section className="chat-panel panel">
        <div className="chat-heading"><div><span className="assistant-orb">✦</span><div><h2>Maintenance Copilot</h2><p>Graph and manual evidence, routed for every question.</p></div></div><span className="live-pill"><i /> READY</span></div>
        <div className="transcript" aria-live="polite">
          {!turns.length && <div className="chat-empty"><span className="empty-orb">✦</span><h3>What do you need to understand?</h3><p>Ask about an asset, dependency, incident, or maintenance procedure.</p><div className="suggestion-list">{suggestions.map((item) => <button key={item} onClick={() => submit(item)}>{item}<span>→</span></button>)}</div></div>}
          {turns.map((turn, index) => <React.Fragment key={index}>
            <div className="message user"><span>YOU</span><p>{turn.question}</p></div>
            {turn.error ? <div className={`alert ${turn.error.type === "offline" ? "danger" : "warning"}`}><b>{turn.error.type === "provider" ? "Provider configuration" : turn.error.type === "offline" ? "Backend unavailable" : "Request failed"}</b>{turn.error.message}</div> : (
              <div className="message assistant">
                <div className="answer-meta"><span>FACILITYGRAPH AI</span><span className="route-pill">Route: {turn.response.route.replace("_ONLY", "").replace("_", " + ")}</span></div>
                <div className="answer-text">{renderAnswer(turn.response.answer, turn.response.unsourced_spans, onMarkerClick)}</div>
                <ConfidenceBadge confidence={turn.response.confidence} citationCount={turn.response.citations.length} />
              </div>
            )}
          </React.Fragment>)}
          {loading && <div className="thinking"><span className="spinner" />Retrieving graph and document evidence…</div>}
        </div>
        <div className="composer"><label htmlFor="maintenance-question" className="sr-only">Ask a maintenance question</label><textarea id="maintenance-question" rows="2" value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); submit(); } }} placeholder="Ask about a device, incident, or procedure…" disabled={loading} /><button className="button button-accent" onClick={() => submit()} disabled={loading || !question.trim()}>Ask AI <span>↑</span></button><small>Answers may require technician review. Evidence and confidence are shown for every response.</small></div>
      </section>
      <CitationPanel citations={latest?.citations || []} highlighted={highlight} />
    </div>
  );
}
