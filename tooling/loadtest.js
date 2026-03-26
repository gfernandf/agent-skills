/**
 * k6 load-test skeleton for the agent-skills HTTP API.
 *
 * Usage:
 *   k6 run loadtest.js                         # defaults
 *   k6 run --env BASE_URL=http://host:9100 loadtest.js
 *   k6 run --env SKILL_ID=text.simple-summarize loadtest.js
 *
 * Prerequisites: k6 installed (https://k6.io/docs/get-started/installation/)
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

// ── custom metrics ────────────────────────────────────────────
const errorRate = new Rate("error_rate");
const executionDuration = new Trend("skill_execution_ms", true);

// ── configuration ─────────────────────────────────────────────
const BASE = __ENV.BASE_URL || "http://127.0.0.1:9100";
const SKILL_ID = __ENV.SKILL_ID || "text.simple-summarize";
const TOKEN = __ENV.AUTH_TOKEN || "";

const headers = {
  "Content-Type": "application/json",
  ...(TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {}),
};

// ── scenarios ─────────────────────────────────────────────────
export const options = {
  scenarios: {
    // 1. Smoke — single user, confirm endpoints are alive
    smoke: {
      executor: "shared-iterations",
      vus: 1,
      iterations: 5,
      maxDuration: "30s",
      exec: "smoke",
      tags: { scenario: "smoke" },
    },

    // 2. Baseline throughput — constant rate
    baseline: {
      executor: "constant-arrival-rate",
      rate: 10, // 10 req/s
      timeUnit: "1s",
      duration: "30s",
      preAllocatedVUs: 10,
      maxVUs: 30,
      exec: "executeSkill",
      startTime: "35s", // after smoke
      tags: { scenario: "baseline" },
    },

    // 3. Concurrent users ramp-up
    ramp: {
      executor: "ramping-vus",
      startVUs: 1,
      stages: [
        { duration: "15s", target: 20 },
        { duration: "30s", target: 20 },
        { duration: "10s", target: 0 },
      ],
      exec: "executeSkill",
      startTime: "70s",
      tags: { scenario: "ramp" },
    },

    // 4. Spike — sudden burst
    spike: {
      executor: "ramping-arrival-rate",
      startRate: 5,
      timeUnit: "1s",
      stages: [
        { duration: "5s", target: 50 },
        { duration: "10s", target: 50 },
        { duration: "5s", target: 5 },
      ],
      preAllocatedVUs: 40,
      maxVUs: 80,
      exec: "executeSkill",
      startTime: "130s",
      tags: { scenario: "spike" },
    },
  },

  thresholds: {
    http_req_duration: ["p(95)<2000", "p(99)<5000"],
    error_rate: ["rate<0.10"],
    skill_execution_ms: ["p(95)<3000"],
  },
};

// ── test functions ────────────────────────────────────────────

/** Smoke: hit health + list endpoints */
export function smoke() {
  const healthRes = http.get(`${BASE}/v1/health/live`);
  check(healthRes, { "health 200": (r) => r.status === 200 });

  const listRes = http.get(`${BASE}/v1/skills/list`, { headers });
  check(listRes, { "list 200": (r) => r.status === 200 });

  const metricsRes = http.get(`${BASE}/v1/metrics`, { headers });
  check(metricsRes, { "metrics 200": (r) => r.status === 200 });

  sleep(0.5);
}

/** Execute a skill and track latency + errors */
export function executeSkill() {
  const payload = JSON.stringify({
    skill_id: SKILL_ID,
    inputs: { text: "The quick brown fox jumps over the lazy dog." },
  });

  const res = http.post(`${BASE}/v1/skills/${SKILL_ID}/execute`, payload, {
    headers,
    tags: { endpoint: "execute" },
  });

  const ok = check(res, {
    "execute 2xx": (r) => r.status >= 200 && r.status < 300,
  });

  errorRate.add(!ok);

  if (res.timings) {
    executionDuration.add(res.timings.duration);
  }

  sleep(0.1);
}
