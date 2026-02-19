import type {
  StudioErrorMetadata,
  StudioLogEvent,
  StudioRunReport,
  StudioStageSummary,
} from "../studio/studioAdapter";

export type MonitoringStageKey =
  | "parse"
  | "map-api"
  | "gen-ui"
  | "fidelity"
  | "sync";

export type MonitoringStageStatus =
  | "pending"
  | "running"
  | "success"
  | "failure"
  | "skipped";

export interface MonitoringStagePolicy {
  key: MonitoringStageKey;
  label: string;
  aliases: readonly string[];
}

export interface MonitoringStageState {
  key: MonitoringStageKey;
  label: string;
  status: MonitoringStageStatus;
  warnings: number;
  errors: number;
  updatedAt: string | null;
}

export type MonitoringStageStateMap = Record<MonitoringStageKey, MonitoringStageState>;

export interface MonitoringTimelineItem {
  id: string;
  title: string;
  description: string;
  timestamp: string;
  tone: "neutral" | "success" | "warning" | "error";
}

export interface MonitoringLogLine extends StudioLogEvent {
  id: string;
}

export type MonitoringRunHistoryStatus = "completed" | "failed" | "cancelled";

export interface MonitoringRunHistoryItem {
  id: string;
  runId: string | null;
  status: MonitoringRunHistoryStatus;
  startedAt: string;
  endedAt: string;
  summaryMessage: string;
}

export interface MonitoringFailureDetail {
  code: string;
  message: string;
  details: string[];
}

export const MONITORING_STAGE_POLICY: readonly MonitoringStagePolicy[] = [
  {
    key: "parse",
    label: "parse",
    aliases: ["parse"],
  },
  {
    key: "map-api",
    label: "map-api",
    aliases: ["map-api", "map_api", "mapapi"],
  },
  {
    key: "gen-ui",
    label: "gen-ui",
    aliases: ["gen-ui", "gen_ui", "genui"],
  },
  {
    key: "fidelity",
    label: "fidelity",
    aliases: ["fidelity", "fidelity-audit", "fidelity_audit"],
  },
  {
    key: "sync",
    label: "sync",
    aliases: ["sync", "sync-preview", "sync_preview", "preview-smoke", "preview_smoke"],
  },
] as const;

const ALIAS_TO_STAGE_KEY = buildAliasStageMap(MONITORING_STAGE_POLICY);

function buildAliasStageMap(
  policy: readonly MonitoringStagePolicy[],
): Map<string, MonitoringStageKey> {
  const mapping = new Map<string, MonitoringStageKey>();
  policy.forEach((item) => {
    item.aliases.forEach((alias) => {
      mapping.set(normalizeToken(alias), item.key);
    });
  });
  return mapping;
}

function normalizeToken(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "");
}

export function createInitialStageStates(): MonitoringStageStateMap {
  return MONITORING_STAGE_POLICY.reduce<MonitoringStageStateMap>(
    (accumulator, stage) => {
      accumulator[stage.key] = {
        key: stage.key,
        label: stage.label,
        status: "pending",
        warnings: 0,
        errors: 0,
        updatedAt: null,
      };
      return accumulator;
    },
    {
      parse: {
        key: "parse",
        label: "parse",
        status: "pending",
        warnings: 0,
        errors: 0,
        updatedAt: null,
      },
      "map-api": {
        key: "map-api",
        label: "map-api",
        status: "pending",
        warnings: 0,
        errors: 0,
        updatedAt: null,
      },
      "gen-ui": {
        key: "gen-ui",
        label: "gen-ui",
        status: "pending",
        warnings: 0,
        errors: 0,
        updatedAt: null,
      },
      fidelity: {
        key: "fidelity",
        label: "fidelity",
        status: "pending",
        warnings: 0,
        errors: 0,
        updatedAt: null,
      },
      sync: {
        key: "sync",
        label: "sync",
        status: "pending",
        warnings: 0,
        errors: 0,
        updatedAt: null,
      },
    },
  );
}

export function findStageKeyByText(value: string): MonitoringStageKey | null {
  const normalized = normalizeToken(value);
  if (normalized.length === 0) {
    return null;
  }

  const direct = ALIAS_TO_STAGE_KEY.get(normalized);
  if (direct) {
    return direct;
  }

  for (const [alias, stage] of ALIAS_TO_STAGE_KEY.entries()) {
    if (normalized.includes(alias)) {
      return stage;
    }
  }
  return null;
}

export function stageStatusFromSummary(
  status: StudioStageSummary["status"],
): MonitoringStageStatus {
  if (status === "success" || status === "failure" || status === "skipped") {
    return status;
  }
  return "pending";
}

export function applyReportToStages(
  previous: MonitoringStageStateMap,
  report: StudioRunReport,
  timestamp: string,
): MonitoringStageStateMap {
  const next: MonitoringStageStateMap = { ...previous };
  report.stageSummaries.forEach((summary) => {
    const stageKey = findStageKeyByText(summary.stage);
    if (!stageKey) {
      return;
    }
    next[stageKey] = {
      ...next[stageKey],
      status: stageStatusFromSummary(summary.status),
      warnings: summary.warnings,
      errors: summary.errors,
      updatedAt: timestamp,
    };
  });

  MONITORING_STAGE_POLICY.forEach((stage) => {
    if (next[stage.key].status === "pending" || next[stage.key].status === "running") {
      next[stage.key] = {
        ...next[stage.key],
        status: "skipped",
        updatedAt: timestamp,
      };
    }
  });

  return next;
}

export function inferStageUpdateFromLog(log: StudioLogEvent): {
  stageKey: MonitoringStageKey;
  status: MonitoringStageStatus;
} | null {
  const stageKey = findStageKeyByText(log.message);
  if (!stageKey) {
    return null;
  }

  const lowered = log.message.toLowerCase();
  if (log.level === "error" || /\bfail(?:ed|ure)?\b|\berror\b/.test(lowered)) {
    return { stageKey, status: "failure" };
  }
  if (/\bskip(?:ped)?\b/.test(lowered)) {
    return { stageKey, status: "skipped" };
  }
  if (/\bcomplete(?:d)?\b|\bsuccess(?:ful|fully)?\b|\bfinished\b/.test(lowered)) {
    return { stageKey, status: "success" };
  }
  if (/\bstart(?:ed)?\b|\brunning\b|\bprogress\b|실행 중|진행 중/.test(lowered)) {
    return { stageKey, status: "running" };
  }
  return { stageKey, status: "running" };
}

export function inferStageUpdateFromStatusMessage(message: string): MonitoringStageKey | null {
  return findStageKeyByText(message);
}

export function toStageList(stages: MonitoringStageStateMap): MonitoringStageState[] {
  return MONITORING_STAGE_POLICY.map((policy) => stages[policy.key]);
}

export function computeProgressPercent(stages: MonitoringStageStateMap): number {
  const orderedStages = toStageList(stages);
  const completedCount = orderedStages.filter(
    (stage) =>
      stage.status === "success" ||
      stage.status === "failure" ||
      stage.status === "skipped",
  ).length;
  const runningCount = orderedStages.filter((stage) => stage.status === "running").length;
  const effective = completedCount + (runningCount > 0 ? 0.5 : 0);
  return Math.round((effective / orderedStages.length) * 100);
}

export function buildFailureDetail(
  report: StudioRunReport | null,
  stages: MonitoringStageStateMap,
  runtimeError: StudioErrorMetadata | null,
): MonitoringFailureDetail | null {
  if (!runtimeError && (!report || report.verdict !== "failure")) {
    return null;
  }

  const message =
    runtimeError?.message ??
    report?.error?.message ??
    report?.summaryMessage ??
    "Migration run failed.";
  const code =
    runtimeError?.code ??
    report?.error?.code ??
    inferErrorCodeFromMessage(message) ??
    "pipeline_failed";

  const details: string[] = [];

  if (runtimeError?.details !== undefined) {
    details.push(`runtime details: ${stringifyDetailValue(runtimeError.details)}`);
  }
  if (report?.error?.details !== undefined) {
    details.push(`report details: ${stringifyDetailValue(report.error.details)}`);
  }
  if (report) {
    details.push(`runId=${report.runId}`);
    details.push(`durationMs=${report.durationMs}`);
  }

  const failedStages = toStageList(stages).filter((stage) => stage.status === "failure");
  if (failedStages.length > 0) {
    details.push(
      `failed stages: ${failedStages
        .map(
          (stage) =>
            `${stage.label} (warnings=${stage.warnings}, errors=${stage.errors})`,
        )
        .join(", ")}`,
    );
  }

  if (details.length === 0) {
    details.push("No additional details.");
  }

  return {
    code,
    message,
    details,
  };
}

function inferErrorCodeFromMessage(message: string): string | null {
  const explicitCodeMatch = message.match(/\b(?:code|error_code)\s*[:=]\s*([a-z0-9_-]+)/i);
  if (explicitCodeMatch) {
    return explicitCodeMatch[1].toLowerCase();
  }

  const bracketedCodeMatch = message.match(/^\[([a-z0-9_-]+)\]/i);
  if (bracketedCodeMatch) {
    return bracketedCodeMatch[1].toLowerCase();
  }

  const knownCodeMatch = message.match(
    /\b([a-z0-9_]+(?:_error|_failed|_exception|_timeout|_not_found|_invalid))\b/i,
  );
  if (knownCodeMatch) {
    return knownCodeMatch[1].toLowerCase();
  }
  return null;
}

function stringifyDetailValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "-";
  }
  if (typeof value === "string") {
    return value;
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}
