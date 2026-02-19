import {
  type ChangeEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Link } from "react-router-dom";

import { LiveMonitoringPanel } from "../components/monitoring/LiveMonitoringPanel";
import {
  applyReportToStages,
  buildFailureDetail,
  createInitialStageStates,
  findStageKeyByText,
  inferStageUpdateFromLog,
  inferStageUpdateFromStatusMessage,
  type MonitoringLogLine,
  type MonitoringRunHistoryItem,
  type MonitoringRunHistoryStatus,
  type MonitoringStageKey,
  type MonitoringStageStatus,
  type MonitoringTimelineItem,
} from "../components/monitoring/monitoringModel";
import {
  createStudioAdapter,
  isStudioAbortError,
  toStudioErrorMetadata,
  type StudioErrorMetadata,
  type StudioRunConfig,
  type StudioRunReport,
  type StudioRunState,
} from "../components/studio/studioAdapter";

const MAX_TIMELINE_ITEMS = 250;
const MAX_LOG_ITEMS = 700;
const MAX_RUN_HISTORY_ITEMS = 12;

const DEFAULT_RUN_CONFIG: StudioRunConfig = {
  sourceXmlPath: "./xml/sample.xml",
  outputPath: "./out",
  previewHostPath: "./preview-host",
  renderMode: "auto",
};

function timelineToneFromState(state: StudioRunState): MonitoringTimelineItem["tone"] {
  if (state === "completed") {
    return "success";
  }
  if (state === "failed") {
    return "error";
  }
  if (state === "running") {
    return "neutral";
  }
  return "warning";
}

function timelineToneFromStageStatus(
  status: MonitoringStageStatus,
): MonitoringTimelineItem["tone"] {
  if (status === "success") {
    return "success";
  }
  if (status === "failure") {
    return "error";
  }
  if (status === "skipped") {
    return "warning";
  }
  return "neutral";
}

function updateBoundedList<T>(prev: T[], nextItem: T, maxItems: number): T[] {
  if (prev.length + 1 <= maxItems) {
    return [...prev, nextItem];
  }
  return [...prev.slice(prev.length + 1 - maxItems), nextItem];
}

function cloneRunConfig(config: StudioRunConfig): StudioRunConfig {
  return {
    sourceXmlPath: config.sourceXmlPath,
    outputPath: config.outputPath,
    previewHostPath: config.previewHostPath,
    renderMode: config.renderMode,
  };
}

interface ConfigFieldProps {
  label: string;
  children: ReactNode;
}

function ConfigField({ label, children }: ConfigFieldProps) {
  return (
    <label className="studio-config-field">
      <span>{label}</span>
      {children}
    </label>
  );
}

export function StudioMonitoringPage() {
  const adapter = useMemo(() => createStudioAdapter(), []);
  const abortRef = useRef<AbortController | null>(null);
  const timelineCounterRef = useRef(0);
  const logCounterRef = useRef(0);
  const historyCounterRef = useRef(0);
  const activeRunIdRef = useRef<string | null>(null);
  const activeRunStartedAtRef = useRef<string | null>(null);

  const [config, setConfig] = useState<StudioRunConfig>(DEFAULT_RUN_CONFIG);
  const [runState, setRunState] = useState<StudioRunState>("idle");
  const [statusMessage, setStatusMessage] = useState<string>("Ready to run migration pipeline.");
  const [runId, setRunId] = useState<string | null>(null);
  const [adapterName, setAdapterName] = useState<string | null>(null);
  const [stages, setStages] = useState(createInitialStageStates);
  const [timeline, setTimeline] = useState<MonitoringTimelineItem[]>([]);
  const [logs, setLogs] = useState<MonitoringLogLine[]>([]);
  const [report, setReport] = useState<StudioRunReport | null>(null);
  const [runtimeError, setRuntimeError] = useState<StudioErrorMetadata | null>(null);
  const [runHistory, setRunHistory] = useState<MonitoringRunHistoryItem[]>([]);
  const [lastRunConfig, setLastRunConfig] = useState<StudioRunConfig | null>(null);
  const [cancelPending, setCancelPending] = useState(false);

  const failureDetail = useMemo(
    () => buildFailureDetail(report, stages, runtimeError),
    [report, stages, runtimeError],
  );

  useEffect(
    () => () => {
      abortRef.current?.abort();
    },
    [],
  );

  const appendTimeline = useCallback(
    (
      title: string,
      description: string,
      tone: MonitoringTimelineItem["tone"],
      timestamp = new Date().toISOString(),
    ) => {
      timelineCounterRef.current += 1;
      const nextItem: MonitoringTimelineItem = {
        id: `timeline-${timelineCounterRef.current}`,
        title,
        description,
        tone,
        timestamp,
      };
      setTimeline((prev) => updateBoundedList(prev, nextItem, MAX_TIMELINE_ITEMS));
    },
    [],
  );

  const appendLog = useCallback((line: Omit<MonitoringLogLine, "id">) => {
    logCounterRef.current += 1;
    const nextLine: MonitoringLogLine = {
      id: `log-${logCounterRef.current}`,
      ...line,
    };
    setLogs((prev) => updateBoundedList(prev, nextLine, MAX_LOG_ITEMS));
  }, []);

  const appendRunHistory = useCallback(
    (item: Omit<MonitoringRunHistoryItem, "id">) => {
      historyCounterRef.current += 1;
      const nextHistory: MonitoringRunHistoryItem = {
        id: `run-history-${historyCounterRef.current}`,
        ...item,
      };
      setRunHistory((prev) => updateBoundedList(prev, nextHistory, MAX_RUN_HISTORY_ITEMS));
    },
    [],
  );

  const setStageStatus = useCallback(
    (
      stageKey: MonitoringStageKey,
      status: MonitoringStageStatus,
      timestamp: string,
      counts?: { warnings?: number; errors?: number },
    ) => {
      setStages((prev) => {
        const current = prev[stageKey];
        const nextWarnings = counts?.warnings ?? current.warnings;
        const nextErrors = counts?.errors ?? current.errors;
        if (
          current.status === status &&
          current.warnings === nextWarnings &&
          current.errors === nextErrors
        ) {
          return prev;
        }
        return {
          ...prev,
          [stageKey]: {
            ...current,
            status,
            warnings: nextWarnings,
            errors: nextErrors,
            updatedAt: timestamp,
          },
        };
      });
    },
    [],
  );

  const resetRunState = useCallback(() => {
    setRunState("running");
    setStatusMessage("Migration run started.");
    setRunId(null);
    setAdapterName(adapter.name);
    setStages(createInitialStageStates());
    setTimeline([]);
    setLogs([]);
    setReport(null);
    setRuntimeError(null);
    timelineCounterRef.current = 0;
    logCounterRef.current = 0;
  }, [adapter.name]);

  const handleFieldChange = useCallback(
    (field: keyof StudioRunConfig) => (event: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
      const value = event.target.value;
      setConfig((prev) => ({
        ...prev,
        [field]: value,
      }));
    },
    [],
  );

  const executeRun = useCallback(
    async (nextConfig: StudioRunConfig) => {
      if (runState === "running") {
        return;
      }

      const submittedConfig = cloneRunConfig(nextConfig);
      const startedAt = new Date().toISOString();

      activeRunStartedAtRef.current = startedAt;
      activeRunIdRef.current = null;
      setLastRunConfig(submittedConfig);

      const controller = new AbortController();
      abortRef.current = controller;
      resetRunState();
      appendTimeline(
        "Run Requested",
        `source=${submittedConfig.sourceXmlPath}, output=${submittedConfig.outputPath}`,
        "neutral",
        startedAt,
      );

      try {
        const result = await adapter.run(
          submittedConfig,
          {
            onRunId: (nextRunId) => {
              if (activeRunIdRef.current === nextRunId) {
                return;
              }
              activeRunIdRef.current = nextRunId;
              setRunId(nextRunId);
              appendTimeline("Run Registered", `runId=${nextRunId}`, "neutral");
            },
            onStatus: (state, message) => {
              const timestamp = new Date().toISOString();
              setRunState(state);
              setStatusMessage(message);

              const stageKey = inferStageUpdateFromStatusMessage(message);
              if (stageKey && state === "running") {
                setStageStatus(stageKey, "running", timestamp);
                appendTimeline(
                  `${stageKey} running`,
                  message,
                  timelineToneFromStageStatus("running"),
                  timestamp,
                );
              } else {
                appendTimeline(
                  `State: ${state}`,
                  message,
                  timelineToneFromState(state),
                  timestamp,
                );
              }
            },
            onLog: (entry) => {
              appendLog({
                level: entry.level,
                message: entry.message,
                timestamp: entry.timestamp,
              });

              const inferred = inferStageUpdateFromLog(entry);
              if (inferred) {
                setStageStatus(inferred.stageKey, inferred.status, entry.timestamp);
                appendTimeline(
                  `${inferred.stageKey} ${inferred.status}`,
                  entry.message,
                  timelineToneFromStageStatus(inferred.status),
                  entry.timestamp,
                );
              }

              if (entry.level === "error") {
                setRuntimeError((prev) =>
                  prev ?? {
                    code: null,
                    message: entry.message,
                  },
                );
              }
            },
            onReport: (nextReport) => {
              const timestamp = new Date().toISOString();
              const reportError = nextReport.error;
              setReport(nextReport);
              setRunId(nextReport.runId);
              setStatusMessage(nextReport.summaryMessage);
              setStages((prev) => applyReportToStages(prev, nextReport, timestamp));

              if (reportError) {
                setRuntimeError((prev) =>
                  prev ?? {
                    code: reportError.code,
                    message: reportError.message,
                    details: reportError.details,
                  },
                );
              }

              appendTimeline(
                "Report Received",
                `${nextReport.verdict}: ${nextReport.summaryMessage}`,
                nextReport.verdict === "success" ? "success" : "error",
                timestamp,
              );

              nextReport.stageSummaries.forEach((summary) => {
                const stageKey = findStageKeyByText(summary.stage);
                if (!stageKey) {
                  return;
                }
                appendTimeline(
                  `${stageKey} ${summary.status}`,
                  `warnings=${summary.warnings}, errors=${summary.errors}`,
                  timelineToneFromStageStatus(summary.status),
                  timestamp,
                );
              });
            },
          },
          controller.signal,
        );

        const endedAt = new Date().toISOString();
        const completedRunId = result.report.runId ?? activeRunIdRef.current;
        const completedStatus: MonitoringRunHistoryStatus =
          result.finalState === "completed" ? "completed" : "failed";

        setRunId(completedRunId);
        setAdapterName(result.adapterName);
        setRunState(result.finalState);
        setStatusMessage(result.report.summaryMessage);

        if (result.report.error) {
          setRuntimeError({
            code: result.report.error.code,
            message: result.report.error.message,
            details: result.report.error.details,
          });
        }

        appendTimeline(
          "Run Finished",
          result.report.summaryMessage,
          result.finalState === "completed" ? "success" : "error",
          endedAt,
        );

        appendRunHistory({
          runId: completedRunId,
          status: completedStatus,
          startedAt,
          endedAt,
          summaryMessage: result.report.summaryMessage,
        });
      } catch (error) {
        const endedAt = new Date().toISOString();
        const activeRunId = activeRunIdRef.current;

        if (isStudioAbortError(error)) {
          setRunState("idle");
          setStatusMessage("Run cancelled by user.");
          appendTimeline(
            "Run Cancelled",
            "사용자 요청으로 실행이 중단되었습니다.",
            "warning",
            endedAt,
          );
          appendRunHistory({
            runId: activeRunId,
            status: "cancelled",
            startedAt,
            endedAt,
            summaryMessage: "Run cancelled by user.",
          });
          return;
        }

        const errorMeta = toStudioErrorMetadata(error);
        setRunState("failed");
        setStatusMessage(errorMeta.message);
        setRuntimeError(errorMeta);
        appendTimeline("Run Failed", errorMeta.message, "error", endedAt);
        appendRunHistory({
          runId: activeRunId,
          status: "failed",
          startedAt,
          endedAt,
          summaryMessage: errorMeta.message,
        });
      } finally {
        abortRef.current = null;
        activeRunStartedAtRef.current = null;
        activeRunIdRef.current = null;
        setCancelPending(false);
      }
    },
    [
      adapter,
      appendLog,
      appendRunHistory,
      appendTimeline,
      resetRunState,
      runState,
      setStageStatus,
    ],
  );

  const handleCancel = useCallback(async () => {
    if (runState !== "running" || cancelPending) {
      return;
    }

    setCancelPending(true);
    const targetRunId = activeRunIdRef.current ?? runId;
    const requestedAt = new Date().toISOString();

    appendTimeline(
      "Cancel Requested",
      targetRunId ? `runId=${targetRunId}` : "active runId not available",
      "warning",
      requestedAt,
    );

    try {
      await adapter.cancel(targetRunId);
      appendTimeline(
        "Cancel API Accepted",
        targetRunId ? `runId=${targetRunId}` : "cancel request acknowledged",
        "warning",
      );
    } catch (error) {
      const errorMeta = toStudioErrorMetadata(error);
      appendTimeline("Cancel API Failed", errorMeta.message, "warning");
      appendLog({
        level: "warn",
        message: `Cancel API failed: ${errorMeta.message}`,
        timestamp: new Date().toISOString(),
      });
    } finally {
      abortRef.current?.abort();
    }
  }, [adapter, appendLog, appendTimeline, cancelPending, runId, runState]);

  const handleRun = useCallback(() => {
    void executeRun(config);
  }, [config, executeRun]);

  const handleRetry = useCallback(() => {
    if (!lastRunConfig || runState === "running") {
      return;
    }
    const retryConfig = cloneRunConfig(lastRunConfig);
    setConfig(retryConfig);
    void executeRun(retryConfig);
  }, [executeRun, lastRunConfig, runState]);

  const runDisabled =
    runState === "running" ||
    config.sourceXmlPath.trim().length === 0 ||
    config.outputPath.trim().length === 0 ||
    config.previewHostPath.trim().length === 0;
  const retryDisabled = runState === "running" || lastRunConfig === null;

  return (
    <main className="studio-monitor-main">
      <div className="studio-monitor-shell">
        <header className="studio-monitor-header">
          <h1>Migration Studio Live Monitoring</h1>
          <p>
            실시간 파이프라인 상태(parse/map-api/gen-ui/fidelity/sync)와 로그 스트림을 확인합니다.
          </p>
          <Link to="/">Go to preview routes</Link>
        </header>

        <section className="studio-config-card">
          <p className="studio-config-title">Run Configuration</p>
          <div className="studio-config-grid">
            <ConfigField label="Source XML Path">
              <input
                type="text"
                value={config.sourceXmlPath}
                onChange={handleFieldChange("sourceXmlPath")}
              />
            </ConfigField>
            <ConfigField label="Output Path">
              <input
                type="text"
                value={config.outputPath}
                onChange={handleFieldChange("outputPath")}
              />
            </ConfigField>
            <ConfigField label="Preview Host Path">
              <input
                type="text"
                value={config.previewHostPath}
                onChange={handleFieldChange("previewHostPath")}
              />
            </ConfigField>
            <ConfigField label="Render Mode">
              <select value={config.renderMode} onChange={handleFieldChange("renderMode")}>
                <option value="auto">auto</option>
                <option value="strict">strict</option>
                <option value="mui">mui</option>
              </select>
            </ConfigField>
          </div>
          <div className="studio-action-row">
            <button type="button" onClick={handleRun} disabled={runDisabled}>
              Start Run
            </button>
            <button
              type="button"
              onClick={handleCancel}
              disabled={runState !== "running" || cancelPending}
            >
              {cancelPending ? "Cancelling..." : "Cancel"}
            </button>
            <button type="button" onClick={handleRetry} disabled={retryDisabled}>
              Retry Last Config
            </button>
          </div>
        </section>

        <LiveMonitoringPanel
          runId={runId}
          adapterName={adapterName}
          runState={runState}
          statusMessage={statusMessage}
          stages={stages}
          timeline={timeline}
          logs={logs}
          runHistory={runHistory}
          errorDetail={failureDetail}
        />
      </div>
    </main>
  );
}
