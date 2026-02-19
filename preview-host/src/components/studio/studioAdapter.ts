export type StudioRenderMode = "strict" | "mui" | "auto";
export type StudioRunState = "idle" | "running" | "completed" | "failed";
export type StudioLogLevel = "info" | "warn" | "error";

export interface StudioRunConfig {
  sourceXmlPath: string;
  outputPath: string;
  previewHostPath: string;
  renderMode: StudioRenderMode;
}

export interface StudioStageSummary {
  stage: string;
  status: "success" | "failure" | "skipped";
  warnings: number;
  errors: number;
}

export interface StudioReportArtifact {
  path?: string;
  body?: string;
}

export interface StudioRunError {
  code: string | null;
  message: string;
  details?: unknown;
}

export interface StudioRunReport {
  runId: string;
  verdict: "success" | "failure";
  summaryMessage: string;
  durationMs: number;
  stageSummaries: StudioStageSummary[];
  markdownReport: StudioReportArtifact;
  jsonReport: StudioReportArtifact;
  error?: StudioRunError;
}

export interface StudioLogEvent {
  level: StudioLogLevel;
  message: string;
  timestamp: string;
}

export interface StudioRunCallbacks {
  onStatus: (state: StudioRunState, message: string) => void;
  onLog: (entry: StudioLogEvent) => void;
  onReport: (report: StudioRunReport) => void;
  onRunId?: (runId: string) => void;
}

export interface StudioRunResult {
  finalState: Extract<StudioRunState, "completed" | "failed">;
  adapterName: string;
  report: StudioRunReport;
}

export interface StudioAdapter {
  readonly name: string;
  run(
    config: StudioRunConfig,
    callbacks: StudioRunCallbacks,
    signal: AbortSignal,
  ): Promise<StudioRunResult>;
  cancel(runId: string | null): Promise<void>;
}

const ORCHESTRATOR_CREATE_PATH = "/jobs";
const LEGACY_API_START_PATH = "/api/studio/migrations";
const API_POLL_INTERVAL_MS = 900;
const API_MAX_POLLS = 200;
const GLOBAL_API_BASE_KEY = "__MIFL_STUDIO_API_BASE_URL__";
const ORCHESTRATOR_STAGE_ORDER = [
  "parse",
  "map_api",
  "gen_ui",
  "fidelity_audit",
  "sync_preview",
  "preview_smoke",
] as const;

interface StudioAdapterErrorOptions {
  code?: string | null;
  details?: unknown;
}

class StudioAdapterError extends Error {
  readonly recoverable: boolean;
  readonly code: string | null;
  readonly details: unknown;

  constructor(message: string, recoverable = false, options: StudioAdapterErrorOptions = {}) {
    super(message);
    this.name = "StudioAdapterError";
    this.recoverable = recoverable;
    this.code = options.code ?? null;
    this.details = options.details;
  }
}

interface ApiLogPayload {
  seq: number | null;
  level: StudioLogLevel;
  message: string;
  timestamp: string;
}

interface ApiReportPayload {
  runId: string;
  verdict: "success" | "failure";
  summaryMessage: string;
  durationMs: number;
  stageSummaries: StudioStageSummary[];
  markdownReport: StudioReportArtifact;
  jsonReport: StudioReportArtifact;
  error?: StudioRunError;
}

interface ApiStatusPayload {
  runId: string | null;
  status: string | null;
  statusMessage: string | null;
  statusUrl: string | null;
  logs: ApiLogPayload[];
  report: ApiReportPayload | null;
}

interface JsonRequestResponse {
  payload: unknown;
  status: number;
}

type CanonicalRunStatus = "queued" | "running" | "succeeded" | "failed" | "canceled";

const RUN_STATUS_TOKEN_MAP: Readonly<Record<string, CanonicalRunStatus>> = {
  accepted: "queued",
  canceled: "canceled",
  cancelled: "canceled",
  completed: "succeeded",
  created: "queued",
  done: "succeeded",
  error: "failed",
  failed: "failed",
  failure: "failed",
  inprogress: "running",
  ok: "succeeded",
  passed: "succeeded",
  pending: "queued",
  processing: "running",
  queued: "queued",
  running: "running",
  submitted: "queued",
  succeeded: "succeeded",
  success: "succeeded",
};

const STAGE_STATUS_TOKEN_MAP: Readonly<Record<string, StudioStageSummary["status"]>> = {
  canceled: "skipped",
  cancelled: "skipped",
  done: "success",
  error: "failure",
  errored: "failure",
  failed: "failure",
  failure: "failure",
  ignored: "skipped",
  na: "skipped",
  notapplicable: "skipped",
  ok: "success",
  pass: "success",
  passed: "success",
  skipped: "skipped",
  success: "success",
  succeeded: "success",
};

const LOG_LEVEL_TOKEN_MAP: Readonly<Record<string, StudioLogLevel>> = {
  debug: "info",
  err: "error",
  error: "error",
  fatal: "error",
  info: "info",
  warning: "warn",
  warn: "warn",
};

const ORCHESTRATOR_STAGE_ORDER_INDEX = new Map<string, number>(
  ORCHESTRATOR_STAGE_ORDER.map((stage, index) => [stage.replace(/_/g, "-"), index]),
);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function toRecordOrNull(value: unknown): Record<string, unknown> | null {
  return isRecord(value) ? value : null;
}

function hasOwn(record: Record<string, unknown>, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(record, key);
}

function resolveApiBase(): string {
  const globalBaseValue = (globalThis as Record<string, unknown>)[GLOBAL_API_BASE_KEY];
  if (typeof globalBaseValue === "string" && globalBaseValue.trim().length > 0) {
    return globalBaseValue;
  }

  const envBaseValue = import.meta.env.VITE_STUDIO_API_BASE_URL;
  return typeof envBaseValue === "string" ? envBaseValue : "";
}

function toStringOrNull(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function toNonEmptyStringOrNull(value: unknown): string | null {
  const raw = toStringOrNull(value);
  if (raw === null) {
    return null;
  }
  const trimmed = raw.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function toNumber(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (trimmed.length === 0) {
      return fallback;
    }
    const parsed = Number(trimmed);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return fallback;
}

function toCount(value: unknown): number {
  if (Array.isArray(value)) {
    return value.length;
  }
  const count = toNumber(value, 0);
  if (!Number.isFinite(count) || count <= 0) {
    return 0;
  }
  return Math.trunc(count);
}

function toStringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((entry) => {
      if (typeof entry === "string") {
        return entry;
      }
      if (!isRecord(entry)) {
        return null;
      }
      return pickString(entry, ["message", "error", "detail", "details"]);
    })
    .filter((entry): entry is string => entry !== null);
}

function pickValue(source: Record<string, unknown>, keys: readonly string[]): unknown {
  for (const key of keys) {
    if (hasOwn(source, key)) {
      return source[key];
    }
  }
  return undefined;
}

function pickString(source: Record<string, unknown>, keys: readonly string[]): string | null {
  for (const key of keys) {
    const value = toNonEmptyStringOrNull(source[key]);
    if (value !== null) {
      return value;
    }
  }
  return null;
}

function pickValueFromRecords(
  sources: readonly (Record<string, unknown> | null)[],
  keys: readonly string[],
): unknown {
  for (const source of sources) {
    if (!source) {
      continue;
    }
    const value = pickValue(source, keys);
    if (value !== undefined) {
      return value;
    }
  }
  return undefined;
}

function pickStringFromRecords(
  sources: readonly (Record<string, unknown> | null)[],
  keys: readonly string[],
): string | null {
  for (const source of sources) {
    if (!source) {
      continue;
    }
    const value = pickString(source, keys);
    if (value !== null) {
      return value;
    }
  }
  return null;
}

function normalizeToken(value: string): string {
  return value.trim().toLowerCase().replace(/[\s_-]+/g, "");
}

function normalizeStageName(value: unknown): string | null {
  const stageName = toNonEmptyStringOrNull(value);
  if (!stageName) {
    return null;
  }
  return stageName.toLowerCase().replace(/[\s_]+/g, "-");
}

function toCanonicalRunStatus(value: unknown): CanonicalRunStatus | null {
  const raw = toNonEmptyStringOrNull(value);
  if (!raw) {
    return null;
  }
  return RUN_STATUS_TOKEN_MAP[normalizeToken(raw)] ?? null;
}

function normalizeRunStatus(value: unknown): string | null {
  const canonical = toCanonicalRunStatus(value);
  if (canonical) {
    return canonical;
  }
  return toNonEmptyStringOrNull(value);
}

function toVerdict(
  value: unknown,
  fallback: StudioRunReport["verdict"] = "success",
): StudioRunReport["verdict"] {
  const canonical = toCanonicalRunStatus(value);
  if (canonical === "succeeded") {
    return "success";
  }
  if (canonical === "failed" || canonical === "canceled") {
    return "failure";
  }

  const token = toNonEmptyStringOrNull(value);
  if (!token) {
    return fallback;
  }
  const normalized = normalizeToken(token);
  if (normalized === "success" || normalized === "ok" || normalized === "passed") {
    return "success";
  }
  if (normalized === "failure" || normalized === "failed" || normalized === "error") {
    return "failure";
  }
  return fallback;
}

function toLogLevel(value: unknown): StudioLogLevel {
  const raw = toNonEmptyStringOrNull(value);
  if (!raw) {
    return "info";
  }
  return LOG_LEVEL_TOKEN_MAP[normalizeToken(raw)] ?? "info";
}

function toStageStatus(
  value: unknown,
  fallback: StudioStageSummary["status"] = "success",
): StudioStageSummary["status"] {
  if (value === "success" || value === "failure" || value === "skipped") {
    return value;
  }
  const raw = toNonEmptyStringOrNull(value);
  if (!raw) {
    return fallback;
  }
  return STAGE_STATUS_TOKEN_MAP[normalizeToken(raw)] ?? fallback;
}

function toRunError(value: unknown): StudioRunError | null {
  if (!isRecord(value)) {
    return null;
  }

  const message = pickString(value, ["message", "error", "detail", "details"]);
  if (!message) {
    return null;
  }

  return {
    code: pickString(value, ["code", "error_code"]),
    message,
    details: pickValue(value, ["details", "detail", "meta"]),
  };
}

function toApiLogs(value: unknown): ApiLogPayload[] {
  const logsValue = Array.isArray(value)
    ? value
    : isRecord(value)
      ? pickValue(value, ["logs", "log_entries", "logEntries", "items", "entries", "events"])
      : null;
  const logs = Array.isArray(logsValue) ? logsValue : [];
  if (logs.length === 0) {
    return [];
  }

  return logs
    .map((entry, index) => {
      if (!isRecord(entry)) {
        return null;
      }
      const message = pickString(entry, ["message", "msg", "text", "event"]);
      if (!message) {
        return null;
      }
      const sequence = toNumber(pickValue(entry, ["seq", "sequence", "index", "id"]), Number.NaN);
      const seq = Number.isFinite(sequence) ? sequence : null;
      return {
        seq,
        level: toLogLevel(pickValue(entry, ["level", "severity", "logLevel", "log_level"])),
        message,
        timestamp: pickString(entry, [
          "timestamp",
          "timestamp_utc",
          "time",
          "created_at_utc",
          "createdAtUtc",
          "updated_at_utc",
        ]) ?? new Date().toISOString(),
        fallbackIndex: index,
      };
    })
    .filter((entry): entry is ApiLogPayload & { fallbackIndex: number } => entry !== null)
    .sort((left, right) => {
      if (left.seq !== null && right.seq !== null) {
        return left.seq - right.seq;
      }
      if (left.seq !== null) {
        return -1;
      }
      if (right.seq !== null) {
        return 1;
      }
      return left.fallbackIndex - right.fallbackIndex;
    })
    .map(({ seq, level, message, timestamp }) => ({
      seq,
      level,
      message,
      timestamp,
    }));
}

function toStageSummary(
  value: unknown,
  fallbackStageName: string | null,
): StudioStageSummary | null {
  if (isRecord(value)) {
    const stage = normalizeStageName(
      pickString(value, ["stage", "stage_name", "name", "key", "id"]) ?? fallbackStageName,
    );
    if (!stage) {
      return null;
    }
    const warnings = toCount(
      pickValue(value, ["warnings", "warning_count", "warningCount", "warning_total", "warningTotal"]),
    );
    const errors = toCount(
      pickValue(value, ["errors", "error_count", "errorCount", "error_total", "errorTotal"]),
    );
    return {
      stage,
      status: toStageStatus(
        pickValue(value, ["status", "state", "result", "outcome"]),
        errors > 0 ? "failure" : "success",
      ),
      warnings,
      errors,
    };
  }

  const stage = normalizeStageName(fallbackStageName);
  if (!stage) {
    return null;
  }
  return {
    stage,
    status: toStageStatus(value, "success"),
    warnings: 0,
    errors: 0,
  };
}

function toStageSummaries(value: unknown): StudioStageSummary[] {
  const entries: Array<{ summary: StudioStageSummary; index: number }> = [];

  if (Array.isArray(value)) {
    value.forEach((entry, index) => {
      const summary = toStageSummary(entry, null);
      if (summary) {
        entries.push({ summary, index });
      }
    });
  } else if (isRecord(value)) {
    Object.entries(value).forEach(([stageName, entry], index) => {
      const summary = toStageSummary(entry, stageName);
      if (summary) {
        entries.push({ summary, index });
      }
    });
  } else {
    return [];
  }

  return entries
    .sort((left, right) => {
      const leftOrder = ORCHESTRATOR_STAGE_ORDER_INDEX.get(left.summary.stage);
      const rightOrder = ORCHESTRATOR_STAGE_ORDER_INDEX.get(right.summary.stage);
      if (leftOrder !== undefined && rightOrder !== undefined) {
        return leftOrder - rightOrder;
      }
      if (leftOrder !== undefined) {
        return -1;
      }
      if (rightOrder !== undefined) {
        return 1;
      }
      return left.index - right.index;
    })
    .map((entry) => entry.summary);
}

function toReportArtifact(
  sources: readonly (Record<string, unknown> | null)[],
  kind: "markdown" | "json",
): StudioReportArtifact {
  const baseSources = sources.filter((source): source is Record<string, unknown> => source !== null);
  if (baseSources.length === 0) {
    return {};
  }

  const nestedSources = baseSources
    .map((source) => toRecordOrNull(source[kind]))
    .filter((source): source is Record<string, unknown> => source !== null);
  const orderedSources = [...nestedSources, ...baseSources];

  const pathKeys =
    kind === "markdown"
      ? [
          "markdownPath",
          "markdown_path",
          "consolidated_summary_markdown",
          "summary_markdown",
          "markdown_report_path",
          "path",
        ]
      : [
          "jsonPath",
          "json_path",
          "consolidated_summary",
          "summary_json",
          "json_report_path",
          "path",
        ];
  const bodyKeys =
    kind === "markdown"
      ? ["markdownBody", "markdown_body", "markdown", "body", "content"]
      : ["jsonBody", "json_body", "json", "body", "content"];

  const path = pickStringFromRecords(orderedSources, pathKeys) ?? undefined;
  const body = pickStringFromRecords(orderedSources, bodyKeys) ?? undefined;

  return {
    path,
    body,
  };
}

function hasReportSignals(value: unknown): value is Record<string, unknown> {
  if (!isRecord(value)) {
    return false;
  }
  return (
    hasOwn(value, "verdict") ||
    hasOwn(value, "overall_status") ||
    hasOwn(value, "summaryMessage") ||
    hasOwn(value, "summary_message") ||
    hasOwn(value, "stageSummaries") ||
    hasOwn(value, "stage_summaries") ||
    hasOwn(value, "stages") ||
    hasOwn(value, "reports") ||
    hasOwn(value, "markdownReport") ||
    hasOwn(value, "jsonReport")
  );
}

function toApiReportPayload(value: unknown): ApiReportPayload | null {
  if (!hasReportSignals(value)) {
    return null;
  }

  const artifacts = toRecordOrNull(value.artifacts);
  const reports =
    toRecordOrNull(pickValue(value, ["reports", "reportFiles", "report_files"])) ??
    toRecordOrNull(artifacts?.reports) ??
    null;
  const stageSource =
    pickValue(value, ["stageSummaries", "stage_summaries", "stages"]) ??
    pickValueFromRecords([artifacts], ["stageSummaries", "stage_summaries", "stages"]);
  const stageSummaries = toStageSummaries(stageSource);
  const stageHasFailure = stageSummaries.some((stage) => stage.status === "failure");

  const verdict = toVerdict(
    pickValue(value, ["verdict", "overall_status", "status", "result"]),
    stageHasFailure ? "failure" : "success",
  );
  const runId =
    pickString(value, ["runId", "run_id", "job_id", "jobId", "id"]) ??
    pickStringFromRecords([artifacts], ["job_id", "run_id", "runId", "id"]) ??
    `api-${Date.now()}`;
  const summaryMessage = pickString(value, [
    "summaryMessage",
    "summary_message",
    "message",
    "statusMessage",
    "status_message",
  ]) ??
    (verdict === "success" ? "Migration run finished successfully." : "Migration run finished with failures.");

  return {
    runId,
    verdict,
    summaryMessage,
    durationMs: toNumber(pickValue(value, ["durationMs", "duration_ms", "duration"])),
    stageSummaries,
    markdownReport: toReportArtifact(
      [toRecordOrNull(value.markdownReport), reports, artifacts],
      "markdown",
    ),
    jsonReport: toReportArtifact(
      [toRecordOrNull(value.jsonReport), reports, artifacts],
      "json",
    ),
    error: toRunError(pickValue(value, ["error", "run_error"])) ?? undefined,
  };
}

function toApiStatusPayload(value: unknown): ApiStatusPayload {
  if (!isRecord(value)) {
    return {
      runId: null,
      status: null,
      statusMessage: null,
      statusUrl: null,
      logs: [],
      report: null,
    };
  }

  const container = toRecordOrNull(value.job);
  const result = toRecordOrNull(value.result);
  const records = [value, container, result] as const;
  const logsSource = pickValueFromRecords(records, [
    "logs",
    "log_entries",
    "logEntries",
    "entries",
    "events",
    "items",
  ]);
  const reportSource =
    pickValueFromRecords([value, container, result], ["report", "summary"]) ??
    (hasReportSignals(value) ? value : null);

  return {
    runId: pickStringFromRecords(records, ["runId", "run_id", "job_id", "jobId", "id"]),
    status: normalizeRunStatus(
      pickValueFromRecords(records, ["status", "state", "job_status", "run_status"]),
    ),
    statusMessage: pickStringFromRecords(records, [
      "statusMessage",
      "status_message",
      "message",
      "detail",
      "details",
    ]),
    statusUrl: pickStringFromRecords(records, [
      "statusUrl",
      "status_url",
      "pollUrl",
      "poll_url",
      "next",
    ]),
    logs: toApiLogs(logsSource),
    report: toApiReportPayload(reportSource),
  };
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function asStudioAdapterError(
  error: unknown,
  fallbackMessage: string,
  recoverable = false,
): StudioAdapterError {
  if (error instanceof StudioAdapterError) {
    return error;
  }
  return new StudioAdapterError(
    `${fallbackMessage}: ${error instanceof Error ? error.message : String(error)}`,
    recoverable,
  );
}

function isRecoverableStatus(status: number): boolean {
  return (
    status === 404 ||
    status === 405 ||
    status === 409 ||
    status === 429 ||
    status === 500 ||
    status === 501 ||
    status === 502 ||
    status === 503 ||
    status === 504
  );
}

function statusToRunState(status: string | null): StudioRunState {
  const canonical = toCanonicalRunStatus(status);
  if (canonical === "succeeded") {
    return "completed";
  }
  if (canonical === "failed" || canonical === "canceled") {
    return "failed";
  }
  if (canonical === "running" || canonical === "queued") {
    return "running";
  }
  if (status === "completed" || status === "success") {
    return "completed";
  }
  if (status === "failed" || status === "failure" || status === "canceled") {
    return "failed";
  }
  return "running";
}

function isTerminalRunStatus(status: string | null): boolean {
  const canonical = toCanonicalRunStatus(status);
  return canonical === "succeeded" || canonical === "failed" || canonical === "canceled";
}

function isAbsoluteHttpUrl(value: string): boolean {
  return /^https?:\/\//i.test(value);
}

function buildApiUrl(path: string): string {
  const normalizedInput = path.trim();
  if (isAbsoluteHttpUrl(normalizedInput)) {
    return normalizedInput;
  }

  const normalizedPath = normalizedInput.startsWith("/") ? normalizedInput : `/${normalizedInput}`;
  const apiBase = resolveApiBase().trim();
  if (apiBase.length === 0) {
    return normalizedPath;
  }

  const normalizedBase = apiBase.endsWith("/") ? apiBase.slice(0, -1) : apiBase;
  return `${normalizedBase}${normalizedPath}`;
}

function createRequestBody(config: StudioRunConfig): Record<string, string> {
  return {
    sourceXmlPath: config.sourceXmlPath,
    outputPath: config.outputPath,
    previewHostPath: config.previewHostPath,
    renderMode: config.renderMode,
  };
}

function createMarkdownBody(config: StudioRunConfig, report: ApiReportPayload): string {
  const stageLines = report.stageSummaries
    .map(
      (stage) =>
        `- ${stage.stage}: ${stage.status} (warnings=${stage.warnings}, errors=${stage.errors})`,
    )
    .join("\n");

  return [
    "# Migration Studio Report",
    "",
    `- run_id: ${report.runId}`,
    `- verdict: ${report.verdict}`,
    `- source_xml: ${config.sourceXmlPath}`,
    `- output_path: ${config.outputPath}`,
    `- preview_host_path: ${config.previewHostPath}`,
    `- render_mode: ${config.renderMode}`,
    `- duration_ms: ${report.durationMs}`,
    "",
    "## Stage Summary",
    stageLines || "- (none)",
  ].join("\n");
}

function createJsonBody(config: StudioRunConfig, report: ApiReportPayload): string {
  return JSON.stringify(
    {
      runId: report.runId,
      verdict: report.verdict,
      sourceXmlPath: config.sourceXmlPath,
      outputPath: config.outputPath,
      previewHostPath: config.previewHostPath,
      renderMode: config.renderMode,
      durationMs: report.durationMs,
      stageSummaries: report.stageSummaries,
      error: report.error ?? null,
    },
    null,
    2,
  );
}

async function sleep(ms: number, signal: AbortSignal): Promise<void> {
  if (signal.aborted) {
    throw new DOMException("Aborted", "AbortError");
  }

  await new Promise<void>((resolve, reject) => {
    const timeoutId = window.setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, ms);

    const onAbort = () => {
      window.clearTimeout(timeoutId);
      signal.removeEventListener("abort", onAbort);
      reject(new DOMException("Aborted", "AbortError"));
    };

    signal.addEventListener("abort", onAbort);
  });
}

async function requestJson(
  url: string,
  init: RequestInit,
  signal: AbortSignal,
): Promise<JsonRequestResponse> {
  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      signal,
      headers: {
        Accept: "application/json",
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...(init.headers ?? {}),
      },
    });
  } catch (error) {
    if (isAbortError(error)) {
      throw error;
    }

    throw new StudioAdapterError(
      `Studio API connection failed: ${error instanceof Error ? error.message : String(error)}`,
      true,
    );
  }

  const rawText = await response.text();
  const payload = rawText.trim().length === 0 ? null : safeJsonParse(rawText);

  if (!response.ok) {
    const structuredError =
      (isRecord(payload) ? toRunError(payload.error) : null) ??
      (isRecord(payload) ? toRunError(payload) : null);
    const errorMessage = structuredError?.message ?? null;
    const errorCode = structuredError?.code ?? null;
    const errorDetails = structuredError?.details;
    const message =
      errorMessage ??
      (isRecord(payload) && typeof payload.message === "string" ? payload.message : null) ??
      (isRecord(payload) && typeof payload.error === "string" ? payload.error : null) ??
      `Studio API request failed with status ${response.status}.`;
    throw new StudioAdapterError(
      errorCode ? `[${errorCode}] ${message}` : message,
      isRecoverableStatus(response.status),
      {
        code: errorCode,
        details: errorDetails,
      },
    );
  }

  return {
    payload,
    status: response.status,
  };
}

function safeJsonParse(text: string): unknown {
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return null;
  }
}

interface CancelRequestCandidate {
  url: string;
  init: RequestInit;
}

async function requestCancelWithCandidates(
  candidates: readonly CancelRequestCandidate[],
): Promise<void> {
  const signal = new AbortController().signal;
  let lastRecoverableError: StudioAdapterError | null = null;

  for (const candidate of candidates) {
    try {
      await requestJson(candidate.url, candidate.init, signal);
      return;
    } catch (error) {
      if (error instanceof StudioAdapterError && error.recoverable) {
        lastRecoverableError = error;
        continue;
      }
      throw error;
    }
  }

  if (lastRecoverableError) {
    throw lastRecoverableError;
  }

  throw new StudioAdapterError(
    "Cancel API endpoint is unavailable.",
    true,
    {
      code: "cancel_endpoint_unavailable",
    },
  );
}

function createOrchestratorJobRequest(config: StudioRunConfig): Record<string, unknown> {
  const outDir = config.outputPath.replace(/\/$/, "");
  return {
    xml_path: config.sourceXmlPath,
    out_dir: outDir,
    api_out_dir: `${outDir}/generated/api`,
    ui_out_dir: `${outDir}/generated/frontend`,
    preview_host_source_dir: config.previewHostPath,
    use_isolated_preview_host: true,
    render_policy_mode: config.renderMode,
    pretty: true,
  };
}

interface OrchestratorJobPayload {
  id: string;
  status: string;
  result: Record<string, unknown> | null;
  error: StudioRunError | null;
}

function inferRunStatusFromResult(
  result: Record<string, unknown> | null,
  error: StudioRunError | null,
): CanonicalRunStatus | null {
  if (error) {
    return "failed";
  }
  if (!result) {
    return null;
  }

  const resultStatus = toCanonicalRunStatus(pickValue(result, ["status", "state", "result"]));
  if (resultStatus) {
    return resultStatus;
  }

  const exitCode = toNumber(pickValue(result, ["exit_code", "exitCode"]), Number.NaN);
  if (!Number.isFinite(exitCode)) {
    return null;
  }
  return exitCode === 0 ? "succeeded" : "failed";
}

function toOrchestratorJobPayload(value: unknown): OrchestratorJobPayload {
  const container = isRecord(value) && isRecord(value.job) ? value.job : value;
  if (!isRecord(container)) {
    throw new StudioAdapterError("Orchestrator API job payload is malformed.", true);
  }

  const id = pickString(container, ["id", "job_id", "jobId", "run_id", "runId"]);
  if (!id) {
    throw new StudioAdapterError("Orchestrator API job payload is missing id.", true, {
      code: "orchestrator_job_id_missing",
    });
  }

  const result = toRecordOrNull(container.result);
  const error = toRunError(container.error);
  const status =
    normalizeRunStatus(pickValue(container, ["status", "state", "job_status", "run_status"])) ??
    inferRunStatusFromResult(result, error) ??
    "queued";

  return {
    id,
    status,
    result,
    error,
  };
}

function toOrchestratorStatusMessage(job: OrchestratorJobPayload): string {
  const status = toCanonicalRunStatus(job.status) ?? job.status;
  if (status === "queued") {
    return "Job queued.";
  }
  if (status === "running") {
    return "Pipeline running.";
  }
  if (status === "succeeded") {
    return "Pipeline completed successfully.";
  }
  if (status === "canceled") {
    return "Pipeline canceled.";
  }
  if (status === "failed") {
    const errorMessage = job.error?.message ?? job.error?.code ?? "Pipeline failed.";
    return errorMessage;
  }
  return `Job status: ${job.status}`;
}

function toOrchestratorStageSummaries(value: unknown): StudioStageSummary[] {
  return toStageSummaries(value);
}

function createOrchestratorMarkdownBody(
  config: StudioRunConfig,
  report: StudioRunReport,
): string {
  const stageLines = report.stageSummaries
    .map(
      (stage) =>
        `- ${stage.stage}: ${stage.status} (warnings=${stage.warnings}, errors=${stage.errors})`,
    )
    .join("\n");

  return [
    "# Migration Studio Report",
    "",
    `- run_id: ${report.runId}`,
    `- verdict: ${report.verdict}`,
    `- source_xml: ${config.sourceXmlPath}`,
    `- output_path: ${config.outputPath}`,
    `- preview_host_path: ${config.previewHostPath}`,
    `- render_mode: ${config.renderMode}`,
    `- duration_ms: ${report.durationMs}`,
    "",
    "## Stage Summary",
    stageLines || "- (none)",
  ].join("\n");
}

function createOrchestratorJsonBody(report: StudioRunReport): string {
  return JSON.stringify(
    {
      runId: report.runId,
      verdict: report.verdict,
      summaryMessage: report.summaryMessage,
      durationMs: report.durationMs,
      stageSummaries: report.stageSummaries,
      error: report.error ?? null,
    },
    null,
    2,
  );
}

function toOrchestratorReport({
  config,
  job,
  artifactsPayload,
  durationMs,
}: {
  config: StudioRunConfig;
  job: OrchestratorJobPayload;
  artifactsPayload: unknown;
  durationMs: number;
}): StudioRunReport {
  const artifactsContainer = toRecordOrNull(artifactsPayload);
  const artifacts = toRecordOrNull(artifactsContainer?.artifacts) ?? artifactsContainer ?? {};
  const reports =
    toRecordOrNull(pickValue(artifacts, ["reports", "reportFiles", "report_files"])) ?? null;
  const stages = pickValue(artifacts, ["stages", "stageSummaries", "stage_summaries"]);
  const errors = toStringList(pickValue(artifacts, ["errors", "error_messages", "failure_reasons"]));
  const warnings = toStringList(pickValue(artifacts, ["warnings", "warning_messages"]));

  const fallbackVerdict: StudioRunReport["verdict"] =
    toCanonicalRunStatus(job.status) === "succeeded" ? "success" : "failure";
  const verdict = toVerdict(
    pickValue(artifacts, ["overall_status", "overallStatus", "status", "verdict"]),
    fallbackVerdict,
  );
  const payloadError = toRunError(pickValue(artifacts, ["error", "run_error"]));
  const reportError: StudioRunError | undefined =
    verdict === "failure"
      ? payloadError ??
        job.error ??
        (errors.length > 0
          ? {
              code: null,
              message: errors[0],
              details: warnings.length > 0 ? { warnings } : undefined,
            }
          : undefined)
      : undefined;
  const summaryMessage =
    pickStringFromRecords(
      [artifacts, artifactsContainer],
      ["summary_message", "summaryMessage", "message", "detail"],
    ) ??
    (verdict === "success"
      ? "Migration run finished successfully."
      : reportError?.message
        ? `Migration run finished with failures: ${reportError.message}`
        : "Migration run finished with failures.");

  const markdownArtifact = toReportArtifact([reports, artifacts], "markdown");
  const jsonArtifact = toReportArtifact([reports, artifacts], "json");

  const report: StudioRunReport = {
    runId:
      pickStringFromRecords([artifacts, artifactsContainer], ["job_id", "run_id", "runId", "id"]) ??
      job.id,
    verdict,
    summaryMessage,
    durationMs,
    stageSummaries: toOrchestratorStageSummaries(stages),
    markdownReport: {
      path: markdownArtifact.path,
      body: "",
    },
    jsonReport: {
      path: jsonArtifact.path,
      body: "",
    },
    error: reportError,
  };

  report.markdownReport = {
    path: report.markdownReport.path,
    body: markdownArtifact.body ?? createOrchestratorMarkdownBody(config, report),
  };
  report.jsonReport = {
    path: report.jsonReport.path,
    body: jsonArtifact.body ?? createOrchestratorJsonBody(report),
  };

  return report;
}

class OrchestratorJobsAdapter implements StudioAdapter {
  readonly name = "orchestrator-jobs-api";
  private activeRunId: string | null = null;

  async run(
    config: StudioRunConfig,
    callbacks: StudioRunCallbacks,
    signal: AbortSignal,
  ): Promise<StudioRunResult> {
    const startedAt = Date.now();
    callbacks.onStatus("running", "Orchestrator API 실행 요청을 전송했습니다.");

    const startResponse = await requestJson(
      buildApiUrl(ORCHESTRATOR_CREATE_PATH),
      {
        method: "POST",
        body: JSON.stringify(createOrchestratorJobRequest(config)),
      },
      signal,
    );
    const createdJob = toOrchestratorJobPayload(startResponse.payload);
    this.activeRunId = createdJob.id;
    callbacks.onRunId?.(createdJob.id);
    callbacks.onStatus(statusToRunState(createdJob.status), toOrchestratorStatusMessage(createdJob));

    const emittedLogKeys = new Set<string>();
    const emitLogBatch = (logs: ApiLogPayload[]) => {
      logs.forEach((log, index) => {
        const key =
          log.seq !== null
            ? `seq:${log.seq}`
            : `fallback:${index}:${log.timestamp}:${log.level}:${log.message}`;
        if (emittedLogKeys.has(key)) {
          return;
        }
        emittedLogKeys.add(key);
        callbacks.onLog({
          level: log.level,
          message: log.message,
          timestamp: log.timestamp,
        });
      });
    };

    let logEndpointUnavailable = false;
    const fetchAndEmitLogs = async () => {
      if (logEndpointUnavailable) {
        return;
      }

      try {
        const logResponse = await requestJson(
          buildApiUrl(`/jobs/${encodeURIComponent(createdJob.id)}/logs`),
          { method: "GET" },
          signal,
        );
        emitLogBatch(toApiLogs(logResponse.payload));
      } catch (error) {
        if (isAbortError(error)) {
          throw error;
        }
        logEndpointUnavailable = true;
        const adapterError = asStudioAdapterError(
          error,
          "Failed to fetch orchestrator logs",
          true,
        );
        callbacks.onLog({
          level: "warn",
          message: `${this.name} logs endpoint unavailable (${adapterError.message}). 상태 폴링만 계속합니다.`,
          timestamp: new Date().toISOString(),
        });
      }
    };

    try {
      for (let pollAttempt = 0; pollAttempt < API_MAX_POLLS; pollAttempt += 1) {
        if (pollAttempt > 0) {
          await sleep(API_POLL_INTERVAL_MS, signal);
        }

        const [jobResponse] = await Promise.all([
          requestJson(
            buildApiUrl(`/jobs/${encodeURIComponent(createdJob.id)}`),
            {
              method: "GET",
            },
            signal,
          ),
          fetchAndEmitLogs(),
        ]);

        const job = toOrchestratorJobPayload(jobResponse.payload);
        callbacks.onStatus(statusToRunState(job.status), toOrchestratorStatusMessage(job));

        if (isTerminalRunStatus(job.status)) {
          let artifactsPayload: unknown = null;
          try {
            const artifactsResponse = await requestJson(
              buildApiUrl(`/jobs/${encodeURIComponent(createdJob.id)}/artifacts`),
              { method: "GET" },
              signal,
            );
            artifactsPayload = artifactsResponse.payload;
          } catch (error) {
            if (isAbortError(error)) {
              throw error;
            }
            const adapterError = asStudioAdapterError(
              error,
              "Failed to fetch orchestrator artifacts",
              true,
            );
            if (!adapterError.recoverable) {
              throw adapterError;
            }
            callbacks.onLog({
              level: "warn",
              message: `${this.name} artifacts endpoint unavailable (${adapterError.message}). job 상태 기준 리포트로 대체합니다.`,
              timestamp: new Date().toISOString(),
            });
          }

          const report = toOrchestratorReport({
            config,
            job,
            artifactsPayload,
            durationMs: Date.now() - startedAt,
          });
          callbacks.onReport(report);
          const finalState: StudioRunResult["finalState"] =
            report.verdict === "success" ? "completed" : "failed";
          callbacks.onStatus(finalState, report.summaryMessage);
          return {
            finalState,
            adapterName: this.name,
            report,
          };
        }
      }

      throw new StudioAdapterError(
        `Orchestrator API 상태 조회가 시간 제한(${API_MAX_POLLS}회) 내에 완료되지 않았습니다.`,
      );
    } finally {
      this.activeRunId = null;
    }
  }

  async cancel(runId: string | null): Promise<void> {
    const targetRunId = runId ?? this.activeRunId;
    if (!targetRunId) {
      throw new StudioAdapterError("Cancel target runId is unavailable.", true, {
        code: "cancel_target_missing",
      });
    }

    await requestCancelWithCandidates([
      {
        url: buildApiUrl(`/jobs/${encodeURIComponent(targetRunId)}/cancel`),
        init: {
          method: "POST",
        },
      },
      {
        url: buildApiUrl(`/jobs/${encodeURIComponent(targetRunId)}`),
        init: {
          method: "DELETE",
        },
      },
    ]);
  }
}

class HttpStudioAdapter implements StudioAdapter {
  readonly name = "studio-api";
  private activeRunId: string | null = null;

  async run(
    config: StudioRunConfig,
    callbacks: StudioRunCallbacks,
    signal: AbortSignal,
  ): Promise<StudioRunResult> {
    callbacks.onStatus("running", "Studio API 실행 요청을 전송했습니다.");

    const startResponse = await requestJson(
      buildApiUrl(LEGACY_API_START_PATH),
      {
        method: "POST",
        body: JSON.stringify(createRequestBody(config)),
      },
      signal,
    );
    const initialStatus = toApiStatusPayload(startResponse.payload);
    const initialRunId = initialStatus.runId;
    if (initialRunId) {
      this.activeRunId = initialRunId;
      callbacks.onRunId?.(initialRunId);
    }

    const emittedLogKeys = new Set<string>();
    const emitLogBatch = (logs: ApiLogPayload[]) => {
      logs.forEach((log, index) => {
        const key = log.seq !== null ? `seq:${log.seq}` : `fallback:${index}:${log.timestamp}:${log.message}`;
        if (emittedLogKeys.has(key)) {
          return;
        }
        emittedLogKeys.add(key);
        callbacks.onLog({
          level: log.level,
          message: log.message,
          timestamp: log.timestamp,
        });
      });
    };

    emitLogBatch(initialStatus.logs);

    if (initialStatus.statusMessage) {
      callbacks.onStatus(statusToRunState(initialStatus.status), initialStatus.statusMessage);
    }

    try {
      if (initialStatus.report) {
        const normalizedReport = normalizeApiReport(config, initialStatus.report);
        callbacks.onRunId?.(normalizedReport.runId);
        callbacks.onReport(normalizedReport);
        const finalState: StudioRunResult["finalState"] =
          normalizedReport.verdict === "success" ? "completed" : "failed";
        callbacks.onStatus(finalState, normalizedReport.summaryMessage);
        return {
          finalState,
          adapterName: this.name,
          report: normalizedReport,
        };
      }

      let runId = initialStatus.runId;
      let pollUrl = initialStatus.statusUrl;
      if (!pollUrl) {
        if (!runId) {
          throw new StudioAdapterError(
            "Studio API 응답에 runId/statusUrl이 없어 상태 조회를 진행할 수 없습니다.",
            true,
            {
              code: "legacy_status_locator_missing",
            },
          );
        }
        pollUrl = `${LEGACY_API_START_PATH}/${encodeURIComponent(runId)}`;
      }

      for (let pollAttempt = 0; pollAttempt < API_MAX_POLLS; pollAttempt += 1) {
        await sleep(API_POLL_INTERVAL_MS, signal);
        const pollResponse = await requestJson(
          buildApiUrl(pollUrl),
          {
            method: "GET",
          },
          signal,
        );
        const polledStatus = toApiStatusPayload(pollResponse.payload);
        emitLogBatch(polledStatus.logs);
        if (!runId && polledStatus.runId) {
          runId = polledStatus.runId;
          this.activeRunId = runId;
          callbacks.onRunId?.(runId);
        }
        if (polledStatus.statusUrl) {
          pollUrl = polledStatus.statusUrl;
        }

        if (polledStatus.statusMessage) {
          callbacks.onStatus(statusToRunState(polledStatus.status), polledStatus.statusMessage);
        }

        if (polledStatus.report) {
          const normalizedReport = normalizeApiReport(config, polledStatus.report);
          callbacks.onRunId?.(normalizedReport.runId);
          callbacks.onReport(normalizedReport);
          const finalState: StudioRunResult["finalState"] =
            normalizedReport.verdict === "success" ? "completed" : "failed";
          callbacks.onStatus(finalState, normalizedReport.summaryMessage);
          return {
            finalState,
            adapterName: this.name,
            report: normalizedReport,
          };
        }

        if (statusToRunState(polledStatus.status) === "failed") {
          throw new StudioAdapterError("Studio API 작업이 실패 상태로 종료되었지만 report가 제공되지 않았습니다.");
        }
      }

      throw new StudioAdapterError(
        `Studio API 상태 조회가 시간 제한(${API_MAX_POLLS}회) 내에 완료되지 않았습니다.`,
      );
    } finally {
      this.activeRunId = null;
    }
  }

  async cancel(runId: string | null): Promise<void> {
    const targetRunId = runId ?? this.activeRunId;
    if (!targetRunId) {
      throw new StudioAdapterError("Cancel target runId is unavailable.", true, {
        code: "cancel_target_missing",
      });
    }

    await requestCancelWithCandidates([
      {
        url: buildApiUrl(`${LEGACY_API_START_PATH}/${encodeURIComponent(targetRunId)}/cancel`),
        init: {
          method: "POST",
        },
      },
      {
        url: buildApiUrl(`${LEGACY_API_START_PATH}/${encodeURIComponent(targetRunId)}:cancel`),
        init: {
          method: "POST",
        },
      },
      {
        url: buildApiUrl(`${LEGACY_API_START_PATH}/${encodeURIComponent(targetRunId)}`),
        init: {
          method: "DELETE",
        },
      },
      {
        url: buildApiUrl(`${LEGACY_API_START_PATH}/cancel`),
        init: {
          method: "POST",
          body: JSON.stringify({
            runId: targetRunId,
          }),
        },
      },
    ]);
  }
}

function normalizeApiReport(config: StudioRunConfig, report: ApiReportPayload): StudioRunReport {
  const markdownBody =
    report.markdownReport.body ?? createMarkdownBody(config, report);
  const jsonBody = report.jsonReport.body ?? createJsonBody(config, report);

  return {
    ...report,
    markdownReport: {
      path: report.markdownReport.path,
      body: markdownBody,
    },
    jsonReport: {
      path: report.jsonReport.path,
      body: jsonBody,
    },
  };
}

class MockStudioAdapter implements StudioAdapter {
  readonly name = "mock-studio";
  private activeRunId: string | null = null;

  async run(
    config: StudioRunConfig,
    callbacks: StudioRunCallbacks,
    signal: AbortSignal,
  ): Promise<StudioRunResult> {
    const startedAt = Date.now();
    const runId = `mock-${startedAt}`;
    this.activeRunId = runId;
    callbacks.onRunId?.(runId);

    callbacks.onStatus("running", "Mock adapter로 파이프라인을 준비합니다.");
    callbacks.onLog({
      level: "warn",
      message: "Studio API 계약이 준비되지 않았거나 접근할 수 없어 mock adapter로 실행합니다.",
      timestamp: new Date().toISOString(),
    });

    const shouldFail = /fail/i.test(config.sourceXmlPath);
    const stagePlan = [
      "parse",
      "map-api",
      "gen-ui",
      "fidelity-audit",
      "sync-preview",
      "preview-smoke",
    ] as const;

    const stageSummaries: StudioStageSummary[] = [];

    for (const stage of stagePlan) {
      await sleep(360, signal);
      callbacks.onStatus("running", `${stage} 단계 실행 중...`);
      callbacks.onLog({
        level: "info",
        message: `[${stage}] started`,
        timestamp: new Date().toISOString(),
      });

      await sleep(360, signal);

      if (shouldFail && stage === "fidelity-audit") {
        callbacks.onLog({
          level: "error",
          message: `[${stage}] strict risk gate failed`,
          timestamp: new Date().toISOString(),
        });
        stageSummaries.push({
          stage,
          status: "failure",
          warnings: 1,
          errors: 1,
        });
        break;
      }

      callbacks.onLog({
        level: "info",
        message: `[${stage}] completed`,
        timestamp: new Date().toISOString(),
      });

      stageSummaries.push({
        stage,
        status: "success",
        warnings: stage === "map-api" ? 1 : 0,
        errors: 0,
      });
    }

    const failed = stageSummaries.some((stage) => stage.status === "failure");
    const durationMs = Date.now() - startedAt;
    const verdict: StudioRunReport["verdict"] = failed ? "failure" : "success";

    try {
      const report: StudioRunReport = {
        runId,
        verdict,
        summaryMessage: failed
          ? "Mock run completed with simulated failure (fidelity-audit)."
          : "Mock run completed successfully.",
        durationMs,
        stageSummaries,
        markdownReport: {
          path: `${config.outputPath.replace(/\/$/, "")}/${runId}.summary.md`,
          body: [
            "# Mock Migration Run",
            "",
            `- run_id: ${runId}`,
            `- render_mode: ${config.renderMode}`,
            `- source_xml: ${config.sourceXmlPath}`,
            `- output_path: ${config.outputPath}`,
            `- preview_host_path: ${config.previewHostPath}`,
            `- verdict: ${verdict}`,
            "",
            "## Stage Summary",
            ...stageSummaries.map(
              (stage) =>
                `- ${stage.stage}: ${stage.status} (warnings=${stage.warnings}, errors=${stage.errors})`,
            ),
          ].join("\n"),
        },
        jsonReport: {
          path: `${config.outputPath.replace(/\/$/, "")}/${runId}.summary.json`,
          body: JSON.stringify(
            {
              runId,
              verdict,
              durationMs,
              input: {
                sourceXmlPath: config.sourceXmlPath,
                outputPath: config.outputPath,
                previewHostPath: config.previewHostPath,
                renderMode: config.renderMode,
              },
              stageSummaries,
              error: failed
                ? {
                    code: "mock_strict_risk_gate_failed",
                    message: "strict risk gate failed",
                    details: { stage: "fidelity-audit" },
                  }
                : null,
            },
            null,
            2,
          ),
        },
        error: failed
          ? {
              code: "mock_strict_risk_gate_failed",
              message: "strict risk gate failed",
              details: { stage: "fidelity-audit" },
            }
          : undefined,
      };

      callbacks.onReport(report);

      const finalState: StudioRunResult["finalState"] = failed ? "failed" : "completed";
      callbacks.onStatus(finalState, report.summaryMessage);

      callbacks.onLog({
        level: failed ? "error" : "info",
        message: failed ? "Mock run failed." : "Mock run succeeded.",
        timestamp: new Date().toISOString(),
      });

      return {
        finalState,
        adapterName: this.name,
        report,
      };
    } finally {
      this.activeRunId = null;
    }
  }

  async cancel(_runId: string | null): Promise<void> {
    this.activeRunId = null;
  }
}

class FallbackStudioAdapter implements StudioAdapter {
  readonly name = "studio-api-with-mock-fallback";

  constructor(
    private readonly primaryAdapter: StudioAdapter,
    private readonly fallbackAdapter: StudioAdapter,
  ) {}

  async run(
    config: StudioRunConfig,
    callbacks: StudioRunCallbacks,
    signal: AbortSignal,
  ): Promise<StudioRunResult> {
    try {
      return await this.primaryAdapter.run(config, callbacks, signal);
    } catch (error) {
      if (isAbortError(error)) {
        throw error;
      }

      const adapterError =
        error instanceof StudioAdapterError
          ? error
          : new StudioAdapterError(
              `Unexpected studio adapter error: ${error instanceof Error ? error.message : String(error)}`,
            );

      if (!adapterError.recoverable) {
        throw adapterError;
      }

      callbacks.onLog({
        level: "warn",
        message: `${this.primaryAdapter.name} unavailable (${adapterError.message}). mock adapter로 전환합니다.`,
        timestamp: new Date().toISOString(),
      });

      callbacks.onStatus("running", "Mock adapter fallback 실행 중...");
      return this.fallbackAdapter.run(config, callbacks, signal);
    }
  }

  async cancel(runId: string | null): Promise<void> {
    try {
      await this.primaryAdapter.cancel(runId);
    } catch (error) {
      if (isAbortError(error)) {
        throw error;
      }

      const adapterError =
        error instanceof StudioAdapterError
          ? error
          : new StudioAdapterError(
              `Unexpected studio adapter error: ${error instanceof Error ? error.message : String(error)}`,
            );

      if (!adapterError.recoverable) {
        throw adapterError;
      }

      await this.fallbackAdapter.cancel(runId);
    }
  }
}

export function createStudioAdapter(): StudioAdapter {
  return new FallbackStudioAdapter(
    new OrchestratorJobsAdapter(),
    new FallbackStudioAdapter(new HttpStudioAdapter(), new MockStudioAdapter()),
  );
}

export function isStudioAbortError(error: unknown): boolean {
  return isAbortError(error);
}

export interface StudioErrorMetadata {
  code: string | null;
  message: string;
  details?: unknown;
}

export function toStudioErrorMetadata(error: unknown): StudioErrorMetadata {
  if (error instanceof StudioAdapterError) {
    return {
      code: error.code,
      message: error.message,
      details: error.details,
    };
  }
  if (error instanceof Error) {
    return {
      code: null,
      message: error.message,
    };
  }
  return {
    code: null,
    message: String(error),
  };
}
