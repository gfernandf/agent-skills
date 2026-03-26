/**
 * @agent-skills/client — TypeScript SDK for agent-skills runtime API.
 *
 * Minimal, zero-dependency client that wraps the agent-skills HTTP API.
 */

// ── Types ──────────────────────────────────────────────────────

export interface ClientConfig {
  baseUrl: string;
  apiKey?: string;
  timeout?: number;
}

export interface SkillExecutionResult {
  skill_id: string;
  status: string;
  outputs: Record<string, unknown>;
  trace_id?: string;
  events?: Array<Record<string, unknown>>;
  step_results?: Record<string, unknown>;
}

export interface SkillSummary {
  id: string;
  name: string;
  description: string;
  domain?: string;
  channel?: string;
  metadata?: Record<string, unknown>;
}

export interface RunStatus {
  run_id: string;
  skill_id: string;
  status: "running" | "completed" | "failed";
  result?: Record<string, unknown>;
  error?: string;
  created_at: string;
  finished_at?: string;
}

export interface DiscoverResult {
  intent: string;
  results: SkillSummary[];
}

export interface PaginatedSkills {
  skills: SkillSummary[];
  pagination: {
    offset: number;
    limit: number;
    total: number;
    has_more: boolean;
    next_offset?: number;
  };
}

export interface HealthResponse {
  status: string;
  checks?: Record<string, unknown>;
}

export interface SSEEvent {
  type: string;
  data: Record<string, unknown>;
}

// ── Client ─────────────────────────────────────────────────────

export class AgentSkillsClient {
  private baseUrl: string;
  private apiKey?: string;
  private timeout: number;

  constructor(config: ClientConfig) {
    this.baseUrl = config.baseUrl.replace(/\/+$/, "");
    this.apiKey = config.apiKey;
    this.timeout = config.timeout ?? 60_000;
  }

  // ── Health ───────────────────────────────────────────────────

  async health(deep = false): Promise<HealthResponse> {
    const url = deep
      ? `${this.baseUrl}/v1/health?deep=true`
      : `${this.baseUrl}/v1/health`;
    return this.get<HealthResponse>(url);
  }

  // ── Skills ───────────────────────────────────────────────────

  async listSkills(options?: {
    domain?: string;
    role?: string;
    status?: string;
    offset?: number;
    limit?: number;
  }): Promise<PaginatedSkills> {
    const params = new URLSearchParams();
    if (options?.domain) params.set("domain", options.domain);
    if (options?.role) params.set("role", options.role);
    if (options?.status) params.set("status", options.status);
    if (options?.offset !== undefined)
      params.set("offset", String(options.offset));
    if (options?.limit !== undefined) params.set("limit", String(options.limit));
    const qs = params.toString();
    return this.get<PaginatedSkills>(
      `${this.baseUrl}/v1/skills/list${qs ? "?" + qs : ""}`
    );
  }

  async describeSkill(skillId: string): Promise<Record<string, unknown>> {
    return this.get(`${this.baseUrl}/v1/skills/${skillId}/describe`);
  }

  async executeSkill(
    skillId: string,
    inputs: Record<string, unknown>,
    options?: {
      traceId?: string;
      includeTrace?: boolean;
      requiredConformanceProfile?: string;
      auditMode?: string;
    }
  ): Promise<SkillExecutionResult> {
    return this.post<SkillExecutionResult>(
      `${this.baseUrl}/v1/skills/${skillId}/execute`,
      {
        inputs,
        trace_id: options?.traceId,
        include_trace: options?.includeTrace,
        required_conformance_profile: options?.requiredConformanceProfile,
        audit_mode: options?.auditMode,
      }
    );
  }

  async executeSkillAsync(
    skillId: string,
    inputs: Record<string, unknown>
  ): Promise<RunStatus> {
    return this.post<RunStatus>(
      `${this.baseUrl}/v1/skills/${skillId}/execute/async`,
      { inputs }
    );
  }

  async discoverSkills(
    intent: string,
    options?: { domain?: string; role?: string; limit?: number }
  ): Promise<DiscoverResult> {
    return this.post<DiscoverResult>(
      `${this.baseUrl}/v1/skills/discover`,
      { intent, ...options }
    );
  }

  // ── Capabilities ─────────────────────────────────────────────

  async executeCapability(
    capabilityId: string,
    inputs: Record<string, unknown>
  ): Promise<Record<string, unknown>> {
    return this.post(
      `${this.baseUrl}/v1/capabilities/${capabilityId}/execute`,
      { inputs }
    );
  }

  // ── Runs ─────────────────────────────────────────────────────

  async getRun(runId: string): Promise<RunStatus> {
    return this.get<RunStatus>(`${this.baseUrl}/v1/runs/${runId}`);
  }

  async waitForRun(
    runId: string,
    options?: { timeoutMs?: number; pollIntervalMs?: number }
  ): Promise<RunStatus> {
    const timeout = options?.timeoutMs ?? 120_000;
    const interval = options?.pollIntervalMs ?? 2_000;
    const deadline = Date.now() + timeout;

    while (Date.now() < deadline) {
      const run = await this.getRun(runId);
      if (run.status !== "running") return run;
      await new Promise((r) => setTimeout(r, interval));
    }
    throw new Error(`Run ${runId} did not complete within ${timeout}ms`);
  }

  // ── SSE Streaming ────────────────────────────────────────────

  async *executeSkillStream(
    skillId: string,
    inputs: Record<string, unknown>
  ): AsyncGenerator<SSEEvent> {
    const resp = await fetch(
      `${this.baseUrl}/v1/skills/${skillId}/execute/stream`,
      {
        method: "POST",
        headers: this.headers(),
        body: JSON.stringify({ inputs }),
        signal: AbortSignal.timeout(this.timeout),
      }
    );
    if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${await resp.text()}`);
    const reader = resp.body?.getReader();
    if (!reader) return;
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() || "";
      for (const part of parts) {
        const event = this.parseSSE(part);
        if (event) yield event;
      }
    }
  }

  // ── Internal ─────────────────────────────────────────────────

  private headers(): Record<string, string> {
    const h: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (this.apiKey) h["Authorization"] = `Bearer ${this.apiKey}`;
    return h;
  }

  private async get<T>(url: string): Promise<T> {
    const resp = await fetch(url, {
      headers: this.headers(),
      signal: AbortSignal.timeout(this.timeout),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${await resp.text()}`);
    return resp.json() as Promise<T>;
  }

  private async post<T>(
    url: string,
    body: Record<string, unknown>
  ): Promise<T> {
    const resp = await fetch(url, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(this.timeout),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${await resp.text()}`);
    return resp.json() as Promise<T>;
  }

  private parseSSE(raw: string): SSEEvent | null {
    const lines = raw.split("\n");
    let eventType = "message";
    let data = "";
    for (const line of lines) {
      if (line.startsWith("event: ")) eventType = line.slice(7).trim();
      else if (line.startsWith("data: ")) data = line.slice(6);
    }
    if (!data) return null;
    try {
      return { type: eventType, data: JSON.parse(data) };
    } catch {
      return { type: eventType, data: { raw: data } };
    }
  }
}
