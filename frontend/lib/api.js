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
    let reason = `Request failed (${response.status})`;
    try {
      const data = await response.json();
      const detail = data.detail;
      if (typeof detail === "string") reason = detail;
      else if (detail?.reason) reason = detail.note ? `${detail.reason} — ${detail.note}` : detail.reason;
      else if (detail?.error) reason = detail.error;
    } catch {
      // Keep the safe status message. Never surface an HTML error page or stack trace.
    }
    throw new ApiError(response.status, reason);
  }

  return response.status === 204 ? null : response.json();
}

export const api = {
  baseUrl: BASE,
  health: () => request("/healthz", { authenticated: false }),
  readiness: () => request("/readyz", { authenticated: false }),
  listUsers: () => request("/users", { authenticated: false }),
  ask: (question, userId) => request("/chat", { method: "POST", body: { question }, userId }),
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
