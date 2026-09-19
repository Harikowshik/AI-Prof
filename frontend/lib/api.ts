const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export interface UserSession {
  token: string;
  email: string;
  fullName: string;
  role: "PLATFORM_ADMIN" | "HOSPITAL_ADMIN" | "CAMPAIGN_MANAGER" | "CLINICAL_REVIEWER";
  hospitalId?: string | null;
  hospitalName?: string | null;
}

export const DEMO_USERS = [
  {
    role: "PLATFORM_ADMIN" as const,
    label: "Platform Admin (Superuser)",
    email: "admin@platform.health",
    password: "PlatformAdmin123!",
    hospitalId: null,
    hospitalName: "All Hospitals (Global)",
  },
  {
    role: "HOSPITAL_ADMIN" as const,
    label: "Hospital Admin (St. Jude)",
    email: "admin@stjude.health",
    password: "HospitalAdmin123!",
    hospitalId: "042327b5-9ad5-4ae0-ae2b-9c5f6625b8fe",
    hospitalName: "St. Jude Hospital",
  },
  {
    role: "CAMPAIGN_MANAGER" as const,
    label: "Campaign Manager (St. Jude)",
    email: "campaigns@stjude.health",
    password: "CampaignMgr123!",
    hospitalId: "042327b5-9ad5-4ae0-ae2b-9c5f6625b8fe",
    hospitalName: "St. Jude Hospital",
  },
  {
    role: "CLINICAL_REVIEWER" as const,
    label: "Clinical Reviewer (Dr. Chen)",
    email: "dr.chen@stjude.health",
    password: "ClinicalRev123!",
    hospitalId: "042327b5-9ad5-4ae0-ae2b-9c5f6625b8fe",
    hospitalName: "St. Jude Hospital",
  },
  {
    role: "HOSPITAL_ADMIN" as const,
    label: "Hospital Admin (Metro General)",
    email: "admin@metro.health",
    password: "HospitalAdmin123!",
    hospitalId: "c54d48ad-a080-4a14-8938-10e4e06a727f",
    hospitalName: "Metro General Hospital",
  },
];

class ApiClient {
  private token: string | null = null;
  private currentUser: UserSession | null = null;

  constructor() {
    if (typeof window !== "undefined") {
      const saved = localStorage.getItem("sachiva_auth");
      if (saved) {
        try {
          this.currentUser = JSON.parse(saved);
          this.token = this.currentUser?.token || null;
        } catch {
          this.clearSession();
        }
      }
    }
  }

  getCurrentUser(): UserSession | null {
    return this.currentUser;
  }

  setSession(session: UserSession) {
    this.currentUser = session;
    this.token = session.token;
    if (typeof window !== "undefined") {
      localStorage.setItem("sachiva_auth", JSON.stringify(session));
    }
  }

  clearSession() {
    this.currentUser = null;
    this.token = null;
    if (typeof window !== "undefined") {
      localStorage.removeItem("sachiva_auth");
    }
  }

  async login(email: string, password: string): Promise<UserSession> {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Authentication failed" }));
      const msg = typeof err.detail === "string" 
        ? err.detail 
        : Array.isArray(err.detail)
        ? err.detail.map((d: any) => d.msg || JSON.stringify(d)).join(", ")
        : JSON.stringify(err.detail || "Authentication failed");
      throw new Error(msg || "Authentication failed");
    }

    const data = await res.json();
    const session: UserSession = {
      token: data.access_token,
      email: data.email || data.user?.email || email,
      fullName: data.full_name || data.user?.full_name || "Healthcare User",
      role: data.role || data.user?.role || "HOSPITAL_ADMIN",
      hospitalId: data.hospital_id ?? data.user?.hospital_id,
      hospitalName: data.hospital_name || data.user?.hospital_name || (data.hospital_id ? "Hospital Workspace" : "Global Platform"),
    };
    this.setSession(session);
    return session;
  }

  private async request<T>(endpoint: string, options: RequestInit & { _retry?: boolean } = {}): Promise<T> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(options.headers as Record<string, string> || {}),
    };

    // Auto-login if no token is present and not currently calling login
    if (!this.token && endpoint !== "/auth/login") {
      try {
        await this.login(DEMO_USERS[1].email, DEMO_USERS[1].password);
      } catch (e) {
        // proceed
      }
    }

    if (this.token) {
      headers["Authorization"] = `Bearer ${this.token}`;
    }

    const res = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers,
    });

    if (res.status === 401 && !options._retry && endpoint !== "/auth/login") {
      this.clearSession();
      try {
        // Transparently acquire fresh demo token and retry once
        await this.login(DEMO_USERS[1].email, DEMO_USERS[1].password);
        return await this.request<T>(endpoint, { ...options, _retry: true });
      } catch (reauthErr) {
        // continue to error
      }
    }

    if (res.status === 401) {
      this.clearSession();
      throw new Error("Session expired. Please switch user or sign in.");
    }

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
      const msg = typeof err.detail === "string" 
        ? err.detail 
        : Array.isArray(err.detail)
        ? err.detail.map((d: any) => d.msg || JSON.stringify(d)).join(", ")
        : JSON.stringify(err.detail || `Request failed with status ${res.status}`);
      throw new Error(msg || `Request failed with status ${res.status}`);
    }

    return res.json();
  }

  // Auth
  async getMe() {
    return this.request<any>("/auth/me");
  }

  // Hospitals
  async getHospitals() {
    return this.request<any[]>("/hospitals");
  }

  async getHospital(id: string) {
    return this.request<any>(`/hospitals/${id}`);
  }

  async updateHospitalCapacity(id: string, maxConcurrentCalls: number) {
    return this.request<any>(`/hospitals/${id}/capacity`, {
      method: "PATCH",
      body: JSON.stringify({ max_concurrent_calls: maxConcurrentCalls }),
    });
  }

  // Dashboard & Analytics
  async getDashboardAnalytics(hospitalId?: string) {
    const query = hospitalId ? `?hospital_id=${encodeURIComponent(hospitalId)}` : "";
    return this.request<any>(`/analytics/dashboard${query}`);
  }

  // Queue Operations
  async getQueueTasks(params?: { status?: string; limit?: number; hospital_id?: string }) {
    const search = new URLSearchParams();
    if (params?.status) search.set("status", params.status);
    if (params?.limit) search.set("limit", params.limit.toString());
    if (params?.hospital_id) search.set("hospital_id", params.hospital_id);
    const q = search.toString() ? `?${search.toString()}` : "";
    return this.request<any>(`/queue/tasks${q}`);
  }

  async getQueueStats(hospitalId?: string) {
    const query = hospitalId ? `?hospital_id=${encodeURIComponent(hospitalId)}` : "";
    return this.request<any>(`/queue/stats${query}`);
  }

  async scheduleNextBatch(limit: number = 3) {
    return this.request<any>("/queue/schedule-next", {
      method: "POST",
      body: JSON.stringify({ limit }),
    });
  }

  async reapStaleTasks() {
    return this.request<any>("/queue/reap-stale", {
      method: "POST",
    });
  }

  // Calls Simulation
  async simulateCall(payload: {
    task_id: string;
    outcome: string;
    scenario?: string;
    custom_transcript?: string;
    callback_minutes?: number;
  }) {
    return this.request<any>("/calls/simulate", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  async getCall(id: string) {
    return this.request<any>(`/calls/${id}`);
  }

  // Patients
  async getPatients(params?: { limit?: number; search?: string; condition?: string }) {
    const search = new URLSearchParams();
    if (params?.limit) search.set("limit", params.limit.toString());
    if (params?.search) search.set("search", params.search);
    if (params?.condition) search.set("condition", params.condition);
    const q = search.toString() ? `?${search.toString()}` : "";
    return this.request<any>(`/patients${q}`);
  }

  async getPatient(id: string) {
    return this.request<any>(`/patients/${id}`);
  }

  // Escalations
  async getEscalations(params?: { status?: string; severity?: string }) {
    const search = new URLSearchParams();
    if (params?.status) search.set("status", params.status);
    if (params?.severity) search.set("severity", params.severity);
    const q = search.toString() ? `?${search.toString()}` : "";
    return this.request<any>(`/escalations${q}`);
  }

  async getEscalation(id: string) {
    return this.request<any>(`/escalations/${id}`);
  }

  async resolveEscalation(id: string, payload: {
    status: "RESOLVED" | "DISMISSED" | "IN_REVIEW";
    clinical_notes: string;
    action_taken: string;
  }) {
    return this.request<any>(`/escalations/${id}/resolve`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  // Campaigns
  async getCampaigns() {
    return this.request<any>("/campaigns");
  }

  async getCampaign(id: string) {
    return this.request<any>(`/campaigns/${id}`);
  }

  async evaluateCampaignEligibility(id: string) {
    return this.request<any>(`/campaigns/${id}/evaluate`, {
      method: "POST",
    });
  }

  async getCampaignWorkload(id: string) {
    return this.request<any>(`/campaigns/${id}/workload`);
  }

  async updateCampaignStatus(id: string, status: "ACTIVE" | "PAUSED" | "DRAFT") {
    return this.request<any>(`/campaigns/${id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    });
  }

  // Protocols
  async getProtocols() {
    return this.request<any>("/protocols");
  }

  // Audit Logs
  async getAuditLogs(params?: { limit?: number; action?: string }) {
    const search = new URLSearchParams();
    if (params?.limit) search.set("limit", params.limit.toString());
    if (params?.action) search.set("action", params.action);
    const q = search.toString() ? `?${search.toString()}` : "";
    return this.request<any>(`/audit${q}`);
  }

  // System Health
  async getHealth() {
    return this.request<any>("/health");
  }

  async getReadiness() {
    return this.request<any>("/ready");
  }
}

export const api = new ApiClient();
