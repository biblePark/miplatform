import type { StudioRunState } from "../studio/studioAdapter";
import {
  computeProgressPercent,
  toStageList,
  type MonitoringLogLine,
  type MonitoringStageStateMap,
  type MonitoringTimelineItem,
} from "./monitoringModel";

interface LiveMonitoringPanelProps {
  runId: string | null;
  adapterName: string | null;
  runState: StudioRunState;
  statusMessage: string;
  stages: MonitoringStageStateMap;
  timeline: MonitoringTimelineItem[];
  logs: MonitoringLogLine[];
  errorDetail: string | null;
}

function toRunStateLabel(state: StudioRunState): string {
  if (state === "running") {
    return "Running";
  }
  if (state === "completed") {
    return "Completed";
  }
  if (state === "failed") {
    return "Failed";
  }
  return "Idle";
}

function toRunStateTone(state: StudioRunState): "neutral" | "success" | "error" {
  if (state === "completed") {
    return "success";
  }
  if (state === "failed") {
    return "error";
  }
  return "neutral";
}

function toStageStatusLabel(status: string): string {
  return status.toUpperCase();
}

function formatTime(value: string | null): string {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleTimeString();
}

export function LiveMonitoringPanel({
  runId,
  adapterName,
  runState,
  statusMessage,
  stages,
  timeline,
  logs,
  errorDetail,
}: LiveMonitoringPanelProps) {
  const progressPercent = computeProgressPercent(stages);
  const stageList = toStageList(stages);
  const runTone = toRunStateTone(runState);

  return (
    <section className="monitoring-panel">
      <div className="monitoring-summary-card">
        <div className="monitoring-summary-row">
          <p className="monitoring-card-title">Execution Monitor</p>
          <span className={`monitoring-run-pill monitoring-run-pill-${runTone}`}>
            {toRunStateLabel(runState)}
          </span>
        </div>
        <p className="monitoring-status-message">{statusMessage}</p>
        <div className="monitoring-meta-row">
          <span>
            runId: <code>{runId ?? "-"}</code>
          </span>
          <span>
            adapter: <code>{adapterName ?? "-"}</code>
          </span>
        </div>
        <div className="monitoring-progress-track">
          <div className="monitoring-progress-fill" style={{ width: `${progressPercent}%` }} />
        </div>
        <p className="monitoring-progress-caption">{progressPercent}% complete</p>
        <div className="monitoring-stage-grid">
          {stageList.map((stage) => (
            <article key={stage.key} className="monitoring-stage-card">
              <div className="monitoring-stage-head">
                <strong>{stage.label}</strong>
                <span className={`monitoring-stage-pill monitoring-stage-pill-${stage.status}`}>
                  {toStageStatusLabel(stage.status)}
                </span>
              </div>
              <p className="monitoring-stage-meta">
                warnings={stage.warnings} | errors={stage.errors}
              </p>
              <p className="monitoring-stage-meta">updated={formatTime(stage.updatedAt)}</p>
            </article>
          ))}
        </div>
      </div>

      {errorDetail ? (
        <section className="monitoring-error-card">
          <p className="monitoring-card-title">Failure Detail</p>
          <pre>{errorDetail}</pre>
        </section>
      ) : null}

      <div className="monitoring-stream-grid">
        <section className="monitoring-stream-card">
          <p className="monitoring-card-title">Status Timeline</p>
          {timeline.length === 0 ? (
            <p className="monitoring-empty-message">No timeline events yet.</p>
          ) : (
            <ol className="monitoring-timeline-list">
              {timeline.map((item) => (
                <li key={item.id} className="monitoring-timeline-item">
                  <div className={`monitoring-dot monitoring-dot-${item.tone}`} />
                  <div className="monitoring-timeline-content">
                    <p className="monitoring-timeline-title">{item.title}</p>
                    <p className="monitoring-timeline-description">{item.description}</p>
                    <p className="monitoring-timeline-time">
                      {new Date(item.timestamp).toLocaleTimeString()}
                    </p>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </section>

        <section className="monitoring-stream-card">
          <p className="monitoring-card-title">Log Stream</p>
          {logs.length === 0 ? (
            <p className="monitoring-empty-message">No log entries yet.</p>
          ) : (
            <ul className="monitoring-log-list">
              {logs.map((log) => (
                <li key={log.id} className={`monitoring-log-line monitoring-log-line-${log.level}`}>
                  <span className="monitoring-log-time">
                    {new Date(log.timestamp).toLocaleTimeString()}
                  </span>
                  <span className={`monitoring-log-level monitoring-log-level-${log.level}`}>
                    {log.level.toUpperCase()}
                  </span>
                  <span className="monitoring-log-message">{log.message}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </section>
  );
}
