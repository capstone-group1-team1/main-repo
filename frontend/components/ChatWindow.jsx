import React, { useState } from "react";
import ReactMarkdown from "react-markdown";
import ConfidenceBadge from "./ConfidenceBadge";
import CitationPanel from "./CitationPanel";

// Citation markers ([1], [2]...) are split out and rendered as clickable
// buttons; everything else is rendered as Markdown (bold, lists, headings)
// via react-markdown. `p: React.Fragment` keeps each segment inline instead
// of wrapping it in its own <p>, since segments sit side-by-side inside one
// answer container. Known limitation: a citation marker landing mid-way
// through a multi-line list can split that list into separate markdown
// fragments — rare in practice since markers trail a clause, not a list
// marker, but noted here rather than hidden.
function renderAnswer(text = "", unsourced = [], onMarkerClick) {
  return text.split(/(\[\d+\])/g).map((part, index) => {
    const marker = part.match(/^\[(\d+)\]$/);
    if (marker) {
      return (
        <button key={index} className="cite-marker" onClick={() => onMarkerClick(Number(marker[1]))}>
          [{marker[1]}]
        </button>
      );
    }
    if (!part) return null;
    const lacksSource = unsourced.some((item) => item.length > 8 && part.includes(item.slice(0, 20)));
    return (
      <span
        key={index}
        className={lacksSource ? "unsourced" : undefined}
        title={lacksSource ? "No retrieved source supports this span" : undefined}
      >
        <ReactMarkdown components={{ p: React.Fragment }}>{part}</ReactMarkdown>
      </span>
    );
  });
}

function safeError(error) {
  const raw = error?.reason || error?.message || "The request could not be completed.";
  // Defense in depth: no matter what shape `raw` turns out to be (api.js
  // should already guarantee a string, but this is the last line of
  // defense against ever handing React a plain object/array as a child —
  // that crashes the whole page with "Objects are not valid as a React
  // child", React error #31).
  const message = typeof raw === "string" ? raw : JSON.stringify(raw);
  const providerProblem = /LLM|xAI|provider|API key|authentication|unauthorized/i.test(message);
  if (providerProblem) return { type: "provider", message: "AI provider is not configured correctly. Verify XAI_API_KEY and GROQ_API_KEY, then restart the API service." };
  if (error?.status === 0 || /offline|reach the backend|interrupted/i.test(message)) return { type: "offline", message: "The backend is offline or the connection dropped. Start the API service, then try again." };
  return { type: "request", message };
}

export default function ChatWindow({ askStream }) {
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState([]);
  const [loading, setLoading] = useState(false);
  const [highlight, setHighlight] = useState(null);
  const suggestions = ["What devices depend on the CP4?", "Show incidents for the meeting room display", "How do I troubleshoot an offline AirMedia receiver?"];

  function updateTurn(index, patch) {
    setTurns((current) => {
      const next = [...current];
      next[index] = typeof patch === "function" ? patch(next[index]) : { ...next[index], ...patch };
      return next;
    });
  }

  async function submit(input = question) {
    const clean = input.trim();
    if (!clean || loading) return;
    setQuestion("");
    setLoading(true);

    const turnIndex = turns.length;
    setTurns((current) => [...current, { question: clean, streaming: true, partialAnswer: "" }]);

    try {
      await askStream(clean, {
        onToken: (text) => {
          updateTurn(turnIndex, (turn) => ({ ...turn, partialAnswer: (turn.partialAnswer || "") + text }));
        },
        onFinal: (finalResponse) => {
          updateTurn(turnIndex, { question: clean, response: finalResponse, streaming: false, partialAnswer: undefined });
          setLoading(false);
          try {
            const existing = JSON.parse(window.localStorage.getItem("facilitygraph.questions") || "[]");
            window.localStorage.setItem("facilitygraph.questions", JSON.stringify([{ question: clean, route: finalResponse.route, at: new Date().toISOString() }, ...existing].slice(0, 8)));
          } catch { /* Recent-question history is a local convenience only. */ }
        },
        onError: (error) => {
          updateTurn(turnIndex, { question: clean, error: safeError(error), streaming: false, partialAnswer: undefined });
          setLoading(false);
        },
      });
    } catch (error) {
      updateTurn(turnIndex, { question: clean, error: safeError(error), streaming: false, partialAnswer: undefined });
      setLoading(false);
    }
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
          {turns.map((turn, index) => {
            const stillThinking = turn.streaming && !turn.partialAnswer;
            const text = turn.response ? turn.response.answer : (turn.partialAnswer || "");
            return (
              <React.Fragment key={index}>
                <div className="message user"><span>YOU</span><p>{turn.question}</p></div>
                {turn.error ? (
                  <div className={`alert ${turn.error.type === "offline" ? "danger" : "warning"}`}><b>{turn.error.type === "provider" ? "Provider configuration" : turn.error.type === "offline" ? "Backend unavailable" : "Request failed"}</b>{turn.error.message}</div>
                ) : stillThinking ? (
                  <div className="thinking"><span className="spinner" />Retrieving graph and document evidence…</div>
                ) : (
                  <div className="message assistant">
                    <div className="answer-meta">
                      <span>FACILITYGRAPH AI</span>
                      {turn.response && <span className="route-pill">Route: {turn.response.route.replace("_ONLY", "").replace("_", " + ")}</span>}
                      {turn.streaming && <span className="live-pill"><i /> STREAMING</span>}
                    </div>
                    <div className="answer-text">
                      {renderAnswer(text, turn.response ? turn.response.unsourced_spans : [], onMarkerClick)}
                      {turn.streaming && <span className="stream-caret" aria-hidden="true" />}
                    </div>
                    {turn.response && <ConfidenceBadge confidence={turn.response.confidence} citationCount={turn.response.citations.length} />}
                  </div>
                )}
              </React.Fragment>
            );
          })}
        </div>
        <div className="composer"><label htmlFor="maintenance-question" className="sr-only">Ask a maintenance question</label><textarea id="maintenance-question" rows="2" maxLength={500} value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); submit(); } }} placeholder="Ask about a device, incident, or procedure…" disabled={loading} /><button className="button button-accent" onClick={() => submit()} disabled={loading || !question.trim()}>Ask AI <span>↑</span></button><small>Answers may require technician review. Evidence and confidence are shown for every response.</small></div>
      </section>
      <CitationPanel citations={latest?.citations || []} highlighted={highlight} />
    </div>
  );
}
