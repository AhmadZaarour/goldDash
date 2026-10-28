export type Role = "admin" | "cashier" | "employee";
export interface User {
  id: number;
  username: string;
  email: string;
  role: Role;
}
export interface Row {
  id: number;
  [key: string]: unknown;
}
export interface Page {
  rows: Row[];
  total: number;
}
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
const base = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
let access = "";
let refreshFlight: Promise<boolean> | null = null;
let expired = () => {};
export function onExpired(fn: () => void) {
  expired = fn;
}
export function clearSession() {
  access = "";
  sessionStorage.removeItem("gold-refresh");
}
function save(tokens: { access_token: string; refresh_token: string }) {
  access = tokens.access_token;
  sessionStorage.setItem("gold-refresh", tokens.refresh_token);
}
export async function renew(): Promise<boolean> {
  if (refreshFlight) return refreshFlight;
  refreshFlight = (async () => {
    const token = sessionStorage.getItem("gold-refresh");
    if (!token) return false;
    try {
      const r = await fetch(base + "/api/v1/auth/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: token }),
      });
      if (!r.ok) {
        clearSession();
        return false;
      }
      save(await r.json());
      return true;
    } catch {
      return false;
    }
  })().finally(() => {
    refreshFlight = null;
  });
  return refreshFlight;
}
export async function login(email: string, password: string) {
  const r = await fetch(base + "/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!r.ok) throw new ApiError(r.status, "Invalid email or password");
  save(await r.json());
  return request<User>("/auth/me");
}
export async function logout() {
  try {
    await request("/auth/logout", {
      method: "POST",
      body: JSON.stringify({
        refresh_token: sessionStorage.getItem("gold-refresh"),
      }),
    });
  } finally {
    clearSession();
  }
}
export async function raw(
  path: string,
  init: RequestInit = {},
  retry = true,
): Promise<Response> {
  const headers = new Headers(init.headers);
  if (access) headers.set("Authorization", `Bearer ${access}`);
  if (typeof init.body === "string")
    headers.set("Content-Type", "application/json");
  const r = await fetch(base + "/api/v1" + path, { ...init, headers });
  if (r.status === 401 && retry && (await renew()))
    return raw(path, init, false);
  if (!r.ok) {
    if (r.status === 401) {
      clearSession();
      expired();
    }
    let detail: unknown;
    try {
      detail = (await r.json()).detail;
    } catch {
      detail = r.statusText;
    }
    const message = Array.isArray(detail)
      ? detail
          .map(
            (x: { loc?: string[]; msg?: string }) =>
              `${x.loc?.slice(1).join(".")}: ${x.msg}`,
          )
          .join(" · ")
      : String(detail || r.statusText);
    throw new ApiError(r.status, message);
  }
  return r;
}
export async function request<T = Row>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  return (await raw(path, init)).json();
}
export const get = <T = Row>(path: string) => request<T>(path);
export async function list(
  path: string,
  params: Record<string, string | number> = {},
): Promise<Page> {
  const search = new URLSearchParams(
    Object.entries(params).map(([k, v]) => [k, String(v)]),
  );
  const r = await raw(path + (path.includes("?") ? "&" : "?") + search);
  const rows: Row[] = await r.json();
  return { rows, total: Number(r.headers.get("X-Total-Count") ?? rows.length) };
}
export async function all(path: string): Promise<Row[]> {
  let rows: Row[] = [];
  for (let offset = 0; ; offset += 100) {
    const p = await list(path, { limit: 100, offset });
    rows = [...rows, ...p.rows];
    if (p.rows.length < 100 || rows.length >= p.total) return rows;
  }
}
export function apiBase() {
  return base;
}
export class Operation {
  private pending = new Map<string, string>();
  async send<T = Row>(
    path: string,
    body: unknown,
    method = "POST",
    headerKey = false,
    bodyKey = false,
  ): Promise<T> {
    const text = path + method + JSON.stringify(body);
    let key = this.pending.get(text);
    if (!key) {
      key = Array.from(crypto.getRandomValues(new Uint8Array(16)), (n) =>
        n.toString(16).padStart(2, "0"),
      ).join("");
      this.pending.set(text, key);
    }
    const payload = bodyKey
      ? { ...(body as object), idempotency_key: key }
      : body;
    const result = await request<T>(path, {
      method,
      body: JSON.stringify(payload),
      headers: headerKey ? { "Idempotency-Key": key } : {},
    });
    this.pending.delete(text);
    return result;
  }
}
