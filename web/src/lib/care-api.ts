export type Medication = {
  name: string;
  dose: string;
  purpose: string;
  times: string[];
  until: string;
  note?: string;
};

export type CarePlan = {
  id: string;
  patient: {
    name: string;
    discharged: string;
    hospital: string;
    diagnosis: string;
    plain: string;
  };
  meds: Medication[];
  appointments: { date: string; day: string; title: string; who: string; time: string }[];
  checklist: string[];
  flags: { level: "confirm" | "missing"; title: string; detail: string }[];
  warnings: string[];
};

export type CheckInResult = {
  text: string;
  outcome?: "monitor" | "review" | "emergency" | null;
  questions?: string[] | null;
  summary?: string | null;
  session_id?: string;
};

const PLAN_KEY = "carebridge.plan";
const SESSION_KEY = "carebridge.session";

const DEFAULT_API = "http://127.0.0.1:8787";

export const apiBase = () => {
  const configured = String(import.meta.env["VITE_CAREBRIDGE_API"] ?? "").replace(/\/$/, "");
  return configured || DEFAULT_API;
};

export function readCachedPlan(): CarePlan | null {
  if (typeof sessionStorage === "undefined") return null;
  const raw = sessionStorage.getItem(PLAN_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as CarePlan;
  } catch {
    return null;
  }
}

export function cachePlan(plan: CarePlan) {
  const previous = readCachedPlan();
  sessionStorage.setItem(PLAN_KEY, JSON.stringify(plan));
  if (!previous || previous.id !== plan.id) sessionStorage.removeItem(SESSION_KEY);
}

export function sessionId() {
  const existing = sessionStorage.getItem(SESSION_KEY);
  if (existing) return existing;
  const created = `carebridge-check-in-${crypto.randomUUID()}`;
  sessionStorage.setItem(SESSION_KEY, created);
  return created;
}

export function rememberSession(id: string) {
  sessionStorage.setItem(SESSION_KEY, id);
}

async function detail(response: Response) {
  try {
    const body = (await response.json()) as { detail?: string };
    return body.detail || response.statusText;
  } catch {
    return response.statusText;
  }
}

export async function uploadDischarge(file: File): Promise<CarePlan> {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch(`${apiBase()}/v1/documents/file`, { method: "POST", body });
  if (!response.ok) throw new Error(await detail(response));
  const plan = (await response.json()) as CarePlan;
  cachePlan(plan);
  return plan;
}

export async function loadActivePlan(): Promise<CarePlan | null> {
  const response = await fetch(`${apiBase()}/v1/plans/latest`);
  if (response.ok) {
    const plan = (await response.json()) as CarePlan;
    cachePlan(plan);
    return plan;
  }
  if (response.status === 404) {
    if (typeof sessionStorage !== "undefined") sessionStorage.removeItem(PLAN_KEY);
    return null;
  }
  const cached = readCachedPlan();
  if (cached) return cached;
  throw new Error(await detail(response));
}

export async function fetchPlan(planId: string): Promise<CarePlan> {
  const response = await fetch(`${apiBase()}/v1/plans/${planId}`);
  if (!response.ok) throw new Error(await detail(response));
  const plan = (await response.json()) as CarePlan;
  cachePlan(plan);
  return plan;
}

export async function postCheckIn(planId: string, message: string): Promise<CheckInResult> {
  const response = await fetch(`${apiBase()}/v1/check-ins`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ plan_id: planId, session_id: sessionId(), message }),
  });
  if (!response.ok) throw new Error(await detail(response));
  const result = (await response.json()) as CheckInResult;
  if (result.session_id) rememberSession(result.session_id);
  return result;
}
