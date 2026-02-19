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

export interface StudioRunReport {
  runId: string;
  verdict: "success" | "failure";
  summaryMessage: string;
  durationMs: number;
  stageSummaries: StudioStageSummary[];
  markdownReport: StudioReportArtifact;
  jsonReport: StudioReportArtifact;
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

class StudioAdapterError extends Error {
  readonly recoverable: boolean;

  constructor(message: string, recoverable = false) {
    super(message);
    this.name = "StudioAdapterError";
    this.recoverable = recoverable;
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function resolveApiBase(): string {
  const globalBaseValue = (globalThis as Record<string, unknown>)[GLOBAL_API_BASE_KEY];
  return typeof globalBaseValue === "string" ? globalBaseValue : "";
}

function toStringOrNull(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function toNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function toLogLevel(value: unknown): StudioLogLevel {
  if (value === "warn" || value === "error" || value === "info") {
    return value;
  }
  return "info";
}

function toStageStatus(value: unknown): StudioStageSummary["status"] {
  if (value === "success" || value === "failure" || value === "skipped") {
    return value;
  }
  if (value === "failed") {
    return "failure";
  }
  return "success";
}

function toApiLogs(value: unknown): ApiLogPayload[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((entry, index) => {
      if (!isRecord(entry)) {
        return null;
      }
      const message = toStringOrNull(entry.message);
      if (!message) {
        return null;
      }
      const sequenceCandidate = entry.seq ?? entry.sequence;
      const seq =
        typeof sequenceCandidate === "number" && Number.isFinite(sequenceCandidate)
          ? sequenceCandidate
          : null;
      return {
        seq,
        level: toLogLevel(entry.level),
        message,
        timestamp:
          toStringOrNull(entry.timestamp) ??
          toStringOrNull(entry.timestamp_utc) ??
          new Date().toISOString(),
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

function toStageSummaries(value: unknown): StudioStageSummary[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((entry) => {
      if (!isRecord(entry)) {
        return null;
      }
      const stage = toStringOrNull(entry.stage);
      if (!stage) {
        return null;
      }
      return {
        stage,
        status: toStageStatus(entry.status),
        warnings: toNumber(entry.warnings),
        errors: toNumber(entry.errors),
      };
    })
    .filter((entry): entry is StudioStageSummary => entry !== null);
}

function toReportArtifact(value: unknown, bodyKey: "markdownBody" | "jsonBody", pathKey: "markdownPath" | "jsonPath"): StudioReportArtifact {
  if (!isRecord(value)) {
    return {};
  }

  const path = toStringOrNull(value[pathKey]) ?? toStringOrNull(value.path) ?? undefined;
  const bodyCandidate = value[bodyKey] ?? value.body;
  const body = typeof bodyCandidate === "string" ? bodyCandidate : undefined;

  return {
    path,
    body,
  };
}

function toApiReportPayload(value: unknown): ApiReportPayload | null {
  if (!isRecord(value)) {
    return null;
  }

  const verdictRaw = value.verdict;
  const verdict = verdictRaw === "failure" ? "failure" : "success";
  const runId = toStringOrNull(value.runId) ?? `api-${Date.now()}`;
  const summaryMessage = toStringOrNull(value.summaryMessage) ??
    (verdict === "success" ? "Migration run finished successfully." : "Migration run finished with failures.");

  return {
    runId,
    verdict,
    summaryMessage,
    durationMs: toNumber(value.durationMs),
    stageSummaries: toStageSummaries(value.stageSummaries),
    markdownReport: toReportArtifact(value.reports, "markdownBody", "markdownPath"),
    jsonReport: toReportArtifact(value.reports, "jsonBody", "jsonPath"),
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

  return {
    runId: toStringOrNull(value.runId),
    status: toStringOrNull(value.status),
    statusMessage: toStringOrNull(value.statusMessage),
    statusUrl: toStringOrNull(value.statusUrl),
    logs: toApiLogs(value.logs),
    report: toApiReportPayload(value.report),
  };
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function isRecoverableStatus(status: number): boolean {
  return status === 404 || status === 405 || status === 501 || status === 503;
}

function statusToRunState(status: string | null): StudioRunState {
  if (status === "completed" || status === "success" || status === "succeeded") {
    return "completed";
  }
  if (status === "failed" || status === "failure" || status === "canceled") {
    return "failed";
  }
  if (status === "running" || status === "queued" || status === "pending") {
    return "running";
  }
  return "running";
}

function buildApiUrl(path: string): string {
  const apiBase = resolveApiBase();
  const normalizedBase = apiBase.endsWith("/") ? apiBase.slice(0, -1) : apiBase;
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
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
    const errorMessage =
      isRecord(payload) && isRecord(payload.error) && typeof payload.error.message === "string"
        ? payload.error.message
        : null;
    const message =
      errorMessage ??
      (isRecord(payload) && typeof payload.message === "string" ? payload.message : null) ??
      (isRecord(payload) && typeof payload.error === "string" ? payload.error : null) ??
      `Studio API request failed with status ${response.status}.`;
    throw new StudioAdapterError(message, isRecoverableStatus(response.status));
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
  error: Record<string, unknown> | null;
}

function toOrchestratorJobPayload(value: unknown): OrchestratorJobPayload {
  const container = isRecord(value) && isRecord(value.job) ? value.job : value;
  if (!isRecord(container)) {
    throw new StudioAdapterError("Orchestrator API job payload is malformed.", true);
  }

  const id = toStringOrNull(container.id);
  const status = toStringOrNull(container.status);
  if (!id || !status) {
    throw new StudioAdapterError("Orchestrator API job payload is missing id/status.", true);
  }

  return {
    id,
    status,
    result: isRecord(container.result) ? container.result : null,
    error: isRecord(container.error) ? container.error : null,
  };
}

function toOrchestratorStatusMessage(job: OrchestratorJobPayload): string {
  if (job.status === "queued") {
    return "Job queued.";
  }
  if (job.status === "running") {
    return "Pipeline running.";
  }
  if (job.status === "succeeded") {
    return "Pipeline completed successfully.";
  }
  if (job.status === "canceled") {
    return "Pipeline canceled.";
  }
  if (job.status === "failed") {
    const errorMessage =
      toStringOrNull(job.error?.message) ??
      toStringOrNull(job.error?.code) ??
      "Pipeline failed.";
    return errorMessage;
  }
  return `Job status: ${job.status}`;
}

function toOrchestratorStageSummaries(value: unknown): StudioStageSummary[] {
  if (!isRecord(value)) {
    return [];
  }

  const entries = Object.entries(value).map(([stageKey, raw]) => {
    if (!isRecord(raw)) {
      return {
        stage: stageKey.replace(/_/g, "-"),
        status: "success" as StudioStageSummary["status"],
        warnings: 0,
        errors: 0,
      };
    }
    const warningCountCandidate = raw.warning_count ?? raw.warnings;
    const errorCountCandidate = raw.error_count ?? raw.errors;
    const warningCount = Array.isArray(warningCountCandidate)
      ? warningCountCandidate.length
      : toNumber(warningCountCandidate);
    const errorCount = Array.isArray(errorCountCandidate)
      ? errorCountCandidate.length
      : toNumber(errorCountCandidate);

    return {
      stage: stageKey.replace(/_/g, "-"),
      status: toStageStatus(raw.status),
      warnings: warningCount,
      errors: errorCount,
    };
  });

  const stageOrder = new Map<string, number>(
    ORCHESTRATOR_STAGE_ORDER.map((stage, index) => [stage.replace(/_/g, "-"), index]),
  );

  return entries.sort((left, right) => {
    const leftOrder = stageOrder.get(left.stage);
    const rightOrder = stageOrder.get(right.stage);
    if (leftOrder !== undefined && rightOrder !== undefined) {
      return leftOrder - rightOrder;
    }
    if (leftOrder !== undefined) {
      return -1;
    }
    if (rightOrder !== undefined) {
      return 1;
    }
    return left.stage.localeCompare(right.stage);
  });
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
  if (!isRecord(artifactsPayload)) {
    throw new StudioAdapterError("Orchestrator artifacts payload is malformed.");
  }

  const artifacts = isRecord(artifactsPayload.artifacts) ? artifactsPayload.artifacts : {};
  const reports = isRecord(artifacts.reports) ? artifacts.reports : {};
  const stages = artifacts.stages;
  const errors = Array.isArray(artifacts.errors)
    ? artifacts.errors.filter((entry): entry is string => typeof entry === "string")
    : [];

  const verdict: StudioRunReport["verdict"] =
    job.status === "succeeded" && toStringOrNull(artifacts.overall_status) === "success"
      ? "success"
      : "failure";
  const summaryMessage =
    verdict === "success"
      ? "Migration run finished successfully."
      : errors.length > 0
        ? `Migration run finished with failures: ${errors[0]}`
        : "Migration run finished with failures.";

  const report: StudioRunReport = {
    runId: job.id,
    verdict,
    summaryMessage,
    durationMs,
    stageSummaries: toOrchestratorStageSummaries(stages),
    markdownReport: {
      body: "",
    },
    jsonReport: {
      path: toStringOrNull(reports.consolidated_summary) ?? undefined,
      body: "",
    },
  };

  report.markdownReport = {
    path:
      toStringOrNull(reports.consolidated_summary_markdown) ??
      toStringOrNull(reports.summary_markdown) ??
      undefined,
    body: createOrchestratorMarkdownBody(config, report),
  };
  report.jsonReport = {
    path: report.jsonReport.path,
    body: createOrchestratorJsonBody(report),
  };

  return report;
}

class OrchestratorJobsAdapter implements StudioAdapter {
  readonly name = "orchestrator-jobs-api";

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

    const fetchAndEmitLogs = async () => {
      const logResponse = await requestJson(
        buildApiUrl(`/jobs/${encodeURIComponent(createdJob.id)}/logs`),
        { method: "GET" },
        signal,
      );
      const logPayload = isRecord(logResponse.payload) ? logResponse.payload.logs : null;
      emitLogBatch(toApiLogs(logPayload));
    };

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

      if (job.status === "succeeded" || job.status === "failed" || job.status === "canceled") {
        const artifactsResponse = await requestJson(
          buildApiUrl(`/jobs/${encodeURIComponent(createdJob.id)}/artifacts`),
          { method: "GET" },
          signal,
        );
        const report = toOrchestratorReport({
          config,
          job,
          artifactsPayload: artifactsResponse.payload,
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
  }
}

class HttpStudioAdapter implements StudioAdapter {
  readonly name = "studio-api";

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

    if (initialStatus.report) {
      const normalizedReport = normalizeApiReport(config, initialStatus.report);
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

    const runId = initialStatus.runId;
    if (!runId) {
      throw new StudioAdapterError("Studio API 응답에 runId가 없어 상태 조회를 진행할 수 없습니다.");
    }

    const pollUrl =
      initialStatus.statusUrl ?? `${LEGACY_API_START_PATH}/${encodeURIComponent(runId)}`;

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

      if (polledStatus.statusMessage) {
        callbacks.onStatus(statusToRunState(polledStatus.status), polledStatus.statusMessage);
      }

      if (polledStatus.report) {
        const normalizedReport = normalizeApiReport(config, polledStatus.report);
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

  async run(
    config: StudioRunConfig,
    callbacks: StudioRunCallbacks,
    signal: AbortSignal,
  ): Promise<StudioRunResult> {
    const startedAt = Date.now();
    const runId = `mock-${startedAt}`;

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
          },
          null,
          2,
        ),
      },
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
