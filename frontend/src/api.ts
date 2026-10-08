export type User = { id: number; email: string; name: string };
export type Member = { id: number; name: string; balance_minor: number };
export type Transfer = { from_user: number; from_name: string; to_user: number; to_name: string; amount_minor: number };
export type Group = {
  id: number; name: string; currency: string; remind_after_days: number; closed: boolean;
  invite_token: string; created_by: number; members: Member[]; my_balance_minor: number; transfers: Transfer[];
};
export type GroupRow = { id: number; name: string; currency: string; closed: boolean; members: number; my_balance_minor: number };
export type Share = { user_id: number; name: string; amount_minor: number; weight: number | null };
export type Expense = {
  id: number; payer_id: number; payer_name: string; amount_minor: number; title: string; category: string;
  spent_on: string; comment: string; split_type: "equal" | "shares" | "exact"; has_receipt: boolean;
  receipt_name: string | null; shares: Share[];
};
export type Settlement = {
  id: number; from_user: number; from_name: string; to_user: number; to_name: string;
  amount_minor: number; status: "pending" | "confirmed" | "rejected"; created_at: string;
};
export type Activity = { id: number; kind: string; actor: string | null; payload: Record<string, any>; created_at: string };
export type Notice = { id: number; kind: string; text: string; read: boolean; created_at: string; group_id: number | null };
export type Report = {
  group: { name: string; currency: string }; expense_count: number; total_spent_minor: number; settled_minor: number;
  by_category: Record<string, number>; members: { id: number; name: string; paid_minor: number; share_minor: number; balance_minor: number }[];
  transfers: Transfer[];
};
export type GlobalBalance = {
  currency: string; net_minor: number; groups: { group_id: number; name: string; balance_minor: number; closed: boolean }[];
  people: { user_id: number; name: string; amount_minor: number }[];
};

// sessionStorage on purpose: every browser tab is its own session, so two people can be tested side by side.
let token: string | null = sessionStorage.getItem("token");
export const getToken = () => token;
export function setToken(t: string | null) {
  token = t;
  if (t) sessionStorage.setItem("token", t);
  else sessionStorage.removeItem("token");
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

const FIELD_LABEL: Record<string, string> = { email: "E-mail", password: "Пароль", name: "Имя", amount_minor: "Сумма", currency: "Валюта" };

/** FastAPI validation errors arrive as a list; show them as one readable line. */
export function errorText(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const field = FIELD_LABEL[String(d.loc?.[d.loc.length - 1])] ?? "";
        const msg = String(d.msg ?? "").replace(/^Value error, /, "");
        return field ? `${field}: ${msg}` : msg;
      })
      .join("; ");
  }
  return fallback;
}

async function call<T>(method: string, path: string, body?: unknown, form?: FormData): Promise<T> {
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(`/api${path}`, { method, headers, body: form ?? (body !== undefined ? JSON.stringify(body) : undefined) });
  if (res.status === 401 && token) {
    setToken(null);
    window.dispatchEvent(new Event("auth-expired"));  // App returns to the login screen instead of showing raw errors
  }
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const data = await res.json();
      msg = errorText(data.detail, msg);
    } catch { /* keep status text */ }
    throw new ApiError(res.status, msg);
  }
  return res.json();
}

export const api = {
  register: (email: string, name: string, password: string) => call<{ token: string; user: User }>("POST", "/auth/register", { email, name, password }),
  login: (email: string, password: string) => call<{ token: string; user: User }>("POST", "/auth/login", { email, password }),
  me: () => call<User>("GET", "/auth/me"),
  logout: () => call("POST", "/auth/logout"),
  groups: () => call<GroupRow[]>("GET", "/groups"),
  createGroup: (name: string, currency: string, remind_after_days: number) => call<Group>("POST", "/groups", { name, currency, remind_after_days }),
  group: (id: number) => call<Group>("GET", `/groups/${id}`),
  patchGroup: (id: number, data: { name?: string; remind_after_days?: number }) => call<Group>("PATCH", `/groups/${id}`, data),
  invite: (id: number, email: string) => call<{ link: string }>("POST", `/groups/${id}/invites`, { email }),
  rotateInviteLink: (id: number) => call<Group>("POST", `/groups/${id}/invite-link/rotate`),
  joinInfo: (t: string) => call<{ name: string; currency: string; closed: boolean }>("GET", `/join/${t}`),
  join: (t: string) => call<Group>("POST", `/join/${t}`),
  expenses: (id: number) => call<Expense[]>("GET", `/groups/${id}/expenses`),
  saveExpense: (gid: number, eid: number | null, body: unknown) =>
    eid ? call<Expense>("PUT", `/groups/${gid}/expenses/${eid}`, body) : call<Expense>("POST", `/groups/${gid}/expenses`, body),
  deleteExpense: (gid: number, eid: number) => call("DELETE", `/groups/${gid}/expenses/${eid}`),
  uploadReceipt: (gid: number, eid: number, file: File) => {
    const f = new FormData();
    f.append("file", file);
    return call("POST", `/groups/${gid}/expenses/${eid}/receipt`, undefined, f);
  },
  receiptUrl: (gid: number, eid: number) => `/api/groups/${gid}/expenses/${eid}/receipt`,
  settlements: (id: number) => call<Settlement[]>("GET", `/groups/${id}/settlements`),
  settle: (gid: number, to_user: number, amount_minor: number) => call<Settlement>("POST", `/groups/${gid}/settlements`, { to_user, amount_minor }),
  confirm: (sid: number) => call<Settlement>("POST", `/settlements/${sid}/confirm`),
  reject: (sid: number) => call<Settlement>("POST", `/settlements/${sid}/reject`),
  activity: (id: number) => call<Activity[]>("GET", `/groups/${id}/activity`),
  report: (id: number) => call<Report>("GET", `/groups/${id}/report`),
  close: (id: number) => call<Report>("POST", `/groups/${id}/close`),
  reopen: (id: number) => call<Group>("POST", `/groups/${id}/reopen`),
  myBalances: () => call<GlobalBalance[]>("GET", "/me/balances"),
  notifications: () => call<Notice[]>("GET", "/notifications"),
  readNotifications: () => call("POST", "/notifications/read"),
  outbox: () => call<{ id: number; subject: string; body: string; created_at: string }[]>("GET", "/me/outbox"),
};

/** Live updates: the server pushes {group_id, kind}; screens refetch on every event. */
export function openStream(onEvent: (e: { type: string; group_id?: number; kind?: string }) => void): () => void {
  if (!token) return () => {};
  const es = new EventSource(`/api/stream?access_token=${encodeURIComponent(token)}`);
  es.onmessage = (m) => {
    try { onEvent(JSON.parse(m.data)); } catch { /* ignore */ }
  };
  // The browser reconnects by itself, but a closed stream means the token was rejected: end the session.
  es.onerror = () => {
    if (es.readyState === EventSource.CLOSED) window.dispatchEvent(new Event("auth-expired"));
  };
  return () => es.close();
}
