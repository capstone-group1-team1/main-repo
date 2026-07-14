const BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export class ApiError extends Error {
  constructor(status, reason) {
    super(reason);
    this.status = status;
    this.reason = reason;
  }
}

function storedUserId() {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("facilitygraph.userId");
}

// Turns a FastAPI error response's `detail` field into a plain STRING no
// matter its shape, so a raw object/array can never end up as a rendered
// React child (React error #31: "Objects are not valid as a React child").
// `detail` can be:
//   - a string (a plain HTTPException(detail="..."))
//   - an object with .reason / .note (our domain-error shape, e.g. 403s)
//   - an object with .error
//   - a LIST of Pydantic validation-error objects, e.g.
//     [{"type":"string_too_short","loc":["body","question"],
//       "msg":"String should have at least 1 character","input":""}]
//     — FastAPI's default shape for a 422 on a malformed request body.
function describeErrorDetail(detail, fallback) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const parts = detail.map((e) => {
      const field = Array.isArray(e?.loc) ? e.loc.filter((p) => p !== "body").join(".") : "";
      return field ? `${field}: ${e.msg}` : e.msg || JSON.stringify(e);
    });
    return parts.length ? parts.join("; ") : fallback;
  }
  if (detail?.reason) return detail.note ? `${detail.reason} — ${detail.note}` : detail.reason;
  if (detail?.error) return detail.error;
  return fallback;
}

async function request(path, { method = "GET", body, userId, authenticated = true } = {}) {
  const headers = { "Content-Type": "application/json" };
  const identity = userId || (authenticated ? storedUserId() : null);
  if (identity) headers["X-Mock-User-Id"] = identity;

  let response;
  try {
    response = await fetch(`${BASE}${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, "Backend offline. Check that the API service is running and try again.");
  }

  if (!response.ok) {
    const fallback = `Request failed (${response.status})`;
    let reason = fallback;
    try {
      const data = await response.json();
      reason = describeErrorDetail(data.detail, fallback);
    } catch {
      // Keep the safe status message. Never surface an HTML error page or stack trace.
    }
    throw new ApiError(response.status, reason);
  }

  return response.status === 204 ? null : response.json();
}

// Server-Sent Events over a plain fetch stream (EventSource can't do POST
// with custom headers, so we read + parse "data: {...}\n\n" frames by hand).
async function streamChat(question, userId, { onToken, onFinal, onError }) {
  const headers = { "Content-Type": "application/json" };
  const identity = userId || storedUserId();
  if (identity) headers["X-Mock-User-Id"] = identity;

  let response;
  try {
    response = await fetch(`${BASE}/chat/stream`, {
      method: "POST",
      headers,
      body: JSON.stringify({ question }),
    });
  } catch {
    onError(new ApiError(0, "Backend offline. Check that the API service is running and try again."));
    return;
  }

  if (!response.ok || !response.body) {
    const fallback = `Request failed (${response.status})`;
    let reason = fallback;
    try {
      const data = await response.json();
      reason = describeErrorDetail(data.detail, fallback);
    } catch {
      // Keep the safe status message.
    }
    onError(new ApiError(response.status, reason));
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let sepIndex;
      while ((sepIndex = buffer.indexOf("\n\n")) !== -1) {
        const rawEvent = buffer.slice(0, sepIndex);
        buffer = buffer.slice(sepIndex + 2);
        const dataLine = rawEvent.split("\n").find((l) => l.startsWith("data:"));
        if (!dataLine) continue;
        let event;
        try {
          event = JSON.parse(dataLine.slice(5).trim());
        } catch {
          continue; // skip a malformed frame rather than aborting the stream
        }
        if (event.type === "token") onToken(event.text);
        else if (event.type === "final") onFinal(event);
        else if (event.type === "error") onError(new ApiError(502, event.detail));
      }
    }
  } catch {
    onError(new ApiError(0, "Connection to the assistant was interrupted."));
  }
}

export const api = {
  baseUrl: BASE,
  health: () => request("/healthz", { authenticated: false }),
  readiness: () => request("/readyz", { authenticated: false }),
  listUsers: () => request("/users", { authenticated: false }),
  ask: (question, userId) => request("/chat", { method: "POST", body: { question }, userId }),
  askStream: (question, userId, handlers) => streamChat(question, userId, handlers),
  listDevices: (userId) => request("/devices", { userId }),
  getDevice: (id, userId) => request(`/device/${encodeURIComponent(id)}`, { userId }),
  getDeviceGraph: (id, userId) => request(`/graph/device/${encodeURIComponent(id)}`, { userId }),
  listIncidents: (userId, params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/incidents${qs ? `?${qs}` : ""}`, { userId });
  },
  createIncident: (body, userId) => request("/incidents", { method: "POST", body, userId }),
  replaceDevice: (body, userId) => request("/devices/replace", { method: "POST", body, userId }),
};
