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
  type MonitoringStageKey,
  type MonitoringStageStatus,
  type MonitoringTimelineItem,
} from "../components/monitoring/monitoringModel";
import {
  createStudioAdapter,
  isStudioAbortError,
  type StudioRunConfig,
  type StudioRunReport,
  type StudioRunState,
} from "../components/studio/studioAdapter";

const MAX_TIMELINE_ITEMS = 250;
const MAX_LOG_ITEMS = 700;

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

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

function updateBoundedList<T>(prev: T[], nextItem: T, maxItems: number): T[] {
  if (prev.length + 1 <= maxItems) {
    return [...prev, nextItem];
  }
  return [...prev.slice(prev.length + 1 - maxItems), nextItem];
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

  const [config, setConfig] = useState<StudioRunConfig>(DEFAULT_RUN_CONFIG);
  const [runState, setRunState] = useState<StudioRunState>("idle");
  const [statusMessage, setStatusMessage] = useState<string>("Ready to run migration pipeline.");
  const [runId, setRunId] = useState<string | null>(null);
  const [adapterName, setAdapterName] = useState<string | null>(null);
  const [stages, setStages] = useState(createInitialStageStates);
  const [timeline, setTimeline] = useState<MonitoringTimelineItem[]>([]);
  const [logs, setLogs] = useState<MonitoringLogLine[]>([]);
  const [report, setReport] = useState<StudioRunReport | null>(null);
  const [runtimeErrorMessage, setRuntimeErrorMessage] = useState<string | null>(null);

  const failureDetail = useMemo(
    () => buildFailureDetail(report, stages, runtimeErrorMessage),
    [report, stages, runtimeErrorMessage],
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
    setRuntimeErrorMessage(null);
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

  const handleCancel = useCallback(() => {
    if (!abortRef.current) {
      return;
    }
    abortRef.current.abort();
  }, []);

  const handleRun = useCallback(async () => {
    if (runState === "running") {
      return;
    }

    const controller = new AbortController();
    abortRef.current = controller;
    resetRunState();
    appendTimeline(
      "Run Requested",
      `source=${config.sourceXmlPath}, output=${config.outputPath}`,
      "neutral",
    );

    try {
      const result = await adapter.run(
        config,
        {
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
              setRuntimeErrorMessage((prev) => prev ?? entry.message);
            }
          },
          onReport: (nextReport) => {
            const timestamp = new Date().toISOString();
            setReport(nextReport);
            setRunId(nextReport.runId);
            setStatusMessage(nextReport.summaryMessage);
            setStages((prev) => applyReportToStages(prev, nextReport, timestamp));

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

      setRunId(result.report.runId);
      setAdapterName(result.adapterName);
      setRunState(result.finalState);
      setStatusMessage(result.report.summaryMessage);
      appendTimeline(
        "Run Finished",
        result.report.summaryMessage,
        result.finalState === "completed" ? "success" : "error",
      );
    } catch (error) {
      if (isStudioAbortError(error)) {
        setRunState("idle");
        setStatusMessage("Run cancelled by user.");
        appendTimeline(
          "Run Cancelled",
          "사용자 요청으로 실행이 중단되었습니다.",
          "warning",
        );
        return;
      }

      const message = getErrorMessage(error);
      setRunState("failed");
      setStatusMessage(message);
      setRuntimeErrorMessage(message);
      appendTimeline("Run Failed", message, "error");
    } finally {
      abortRef.current = null;
    }
  }, [adapter, appendLog, appendTimeline, config, resetRunState, runState, setStageStatus]);

  const runDisabled =
    runState === "running" ||
    config.sourceXmlPath.trim().length === 0 ||
    config.outputPath.trim().length === 0 ||
    config.previewHostPath.trim().length === 0;

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
            <button type="button" onClick={handleCancel} disabled={runState !== "running"}>
              Cancel
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
          errorDetail={failureDetail}
        />
      </div>
    </main>
  );
}
