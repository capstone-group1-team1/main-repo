export const DEMO_ROLES = {
  operator: { id: "u-omar", name: "Omar", label: "Operator" },
  technician: { id: "u-ali", name: "Ali", label: "Technician" },
  admin: { id: "u-amer", name: "Amer", label: "Admin" },
};

const KEYS = {
  userId: "facilitygraph.userId",
  role: "facilitygraph.role",
  profile: "facilitygraph.profile",
};

export function getSession() {
  if (typeof window === "undefined") return null;
  const role = window.localStorage.getItem(KEYS.role);
  const userId = window.localStorage.getItem(KEYS.userId);
  if (!role || !userId || !DEMO_ROLES[role] || DEMO_ROLES[role].id !== userId) return null;
  let profile = null;
  try { profile = JSON.parse(window.localStorage.getItem(KEYS.profile) || "null"); } catch { /* ignore invalid demo data */ }
  return { userId, role, ...DEMO_ROLES[role], profile };
}

export function saveSession(role, profile = null) {
  const selected = DEMO_ROLES[role] || DEMO_ROLES.operator;
  window.localStorage.setItem(KEYS.userId, selected.id);
  window.localStorage.setItem(KEYS.role, role in DEMO_ROLES ? role : "operator");
  if (profile) {
    const safeProfile = {
      fullName: profile.fullName || "",
      email: profile.email || "",
      organization: profile.organization || "",
      role: role in DEMO_ROLES ? role : "operator",
    };
    window.localStorage.setItem(KEYS.profile, JSON.stringify(safeProfile));
  }
  window.dispatchEvent(new Event("facilitygraph-session"));
  return getSession();
}

export function clearSession() {
  window.localStorage.removeItem(KEYS.userId);
  window.localStorage.removeItem(KEYS.role);
  window.dispatchEvent(new Event("facilitygraph-session"));
}
