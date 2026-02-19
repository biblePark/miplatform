import { type FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import {
  createStudioAdapter,
  isStudioAbortError,
  type StudioLogEvent,
  type StudioRenderMode,
  type StudioRunConfig,
  type StudioRunReport,
  type StudioRunState,
} from "./studioAdapter";

type ReportTab = "summary" | "markdown" | "json";

interface UiLogEntry extends StudioLogEvent {
  id: number;
}

const STATE_LABEL: Record<StudioRunState, string> = {
  idle: "대기",
  running: "실행",
  completed: "완료",
  failed: "실패",
};

const DEFAULT_CONFIG: StudioRunConfig = {
  sourceXmlPath: "data/input.xml",
  outputPath: "out/studio",
  previewHostPath: "preview-host",
  renderMode: "auto",
};

function formatClock(isoTimestamp: string): string {
  const date = new Date(isoTimestamp);
  return Number.isNaN(date.getTime())
    ? isoTimestamp
    : date.toLocaleTimeString("ko-KR", {
        hour12: false,
      });
}

function createDataUrl(content: string, mimeType: string): string {
  return `data:${mimeType};charset=utf-8,${encodeURIComponent(content)}`;
}

function inferStateFromReport(report: StudioRunReport): Extract<StudioRunState, "completed" | "failed"> {
  return report.verdict === "success" ? "completed" : "failed";
}

export function MigrationStudioShell() {
  const adapter = useMemo(() => createStudioAdapter(), []);
  const abortControllerRef = useRef<AbortController | null>(null);
  const logIdRef = useRef(0);

  const [formConfig, setFormConfig] = useState<StudioRunConfig>(DEFAULT_CONFIG);
  const [runState, setRunState] = useState<StudioRunState>("idle");
  const [statusMessage, setStatusMessage] = useState("실행 대기 중입니다.");
  const [adapterName, setAdapterName] = useState<string>("-");
  const [logs, setLogs] = useState<UiLogEntry[]>([]);
  const [report, setReport] = useState<StudioRunReport | null>(null);
  const [activeTab, setActiveTab] = useState<ReportTab>("summary");
  const [startedAt, setStartedAt] = useState<string | null>(null);
  const [endedAt, setEndedAt] = useState<string | null>(null);

  const markdownBody = report?.markdownReport.body ?? "";
  const jsonBody = report?.jsonReport.body ?? "";

  const markdownDataUrl = markdownBody
    ? createDataUrl(markdownBody, "text/markdown")
    : null;
  const jsonDataUrl = jsonBody ? createDataUrl(jsonBody, "application/json") : null;

  const hasMissingRequiredField =
    formConfig.sourceXmlPath.trim().length === 0 ||
    formConfig.outputPath.trim().length === 0 ||
    formConfig.previewHostPath.trim().length === 0;

  const appendLog = (entry: StudioLogEvent) => {
    logIdRef.current += 1;
    setLogs((previous) => {
      const next = [...previous, { ...entry, id: logIdRef.current }];
      return next.length > 400 ? next.slice(next.length - 400) : next;
    });
  };

  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  const handleInputChange = (field: keyof StudioRunConfig, value: string) => {
    setFormConfig((previous) => ({
      ...previous,
      [field]: value,
    }));
  };

  const handleRenderModeChange = (value: StudioRenderMode) => {
    setFormConfig((previous) => ({
      ...previous,
      renderMode: value,
    }));
  };

  const handleRunStart = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (runState === "running") {
      return;
    }

    if (hasMissingRequiredField) {
      setRunState("failed");
      setStatusMessage("필수 경로를 모두 입력해야 실행할 수 있습니다.");
      appendLog({
        level: "error",
        message: "실행 실패: 필수 입력값이 누락되었습니다.",
        timestamp: new Date().toISOString(),
      });
      return;
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;

    setRunState("running");
    setStatusMessage("변환 실행을 시작합니다...");
    setStartedAt(new Date().toISOString());
    setEndedAt(null);
    setReport(null);
    setActiveTab("summary");
    setLogs([]);
    setAdapterName("(실행 중)");

    appendLog({
      level: "info",
      message: `Run requested: source=${formConfig.sourceXmlPath}, mode=${formConfig.renderMode}`,
      timestamp: new Date().toISOString(),
    });

    try {
      const result = await adapter.run(
        formConfig,
        {
          onStatus: (state, message) => {
            setRunState(state);
            setStatusMessage(message);
          },
          onLog: (entry) => {
            appendLog(entry);
          },
          onReport: (nextReport) => {
            setReport(nextReport);
          },
        },
        controller.signal,
      );

      setAdapterName(result.adapterName);
      setRunState(result.finalState);
      setStatusMessage(result.report.summaryMessage);
      setEndedAt(new Date().toISOString());
      setReport(result.report);
    } catch (error) {
      if (isStudioAbortError(error)) {
        setRunState("idle");
        setStatusMessage("실행이 취소되었습니다.");
        appendLog({
          level: "warn",
          message: "사용자 취소로 실행이 중단되었습니다.",
          timestamp: new Date().toISOString(),
        });
      } else {
        const message = error instanceof Error ? error.message : String(error);
        setRunState("failed");
        setStatusMessage(`실행 실패: ${message}`);
        appendLog({
          level: "error",
          message: `실행 실패: ${message}`,
          timestamp: new Date().toISOString(),
        });
      }
      setEndedAt(new Date().toISOString());
      setAdapterName(adapter.name);
    } finally {
      abortControllerRef.current = null;
    }
  };

  const handleCancel = () => {
    if (runState !== "running") {
      return;
    }
    abortControllerRef.current?.abort();
  };

  const stageRows = report?.stageSummaries ?? [];
  const reportState = report ? inferStateFromReport(report) : null;

  return (
    <main className="studio-main">
      <div className="studio-shell">
        <header className="studio-header">
          <h1 className="studio-title">Migration Studio Shell</h1>
          <p className="studio-subtitle">
            XML -&gt; React 마이그레이션 실행/관리를 위한 GUI 스켈레톤
          </p>
          <p className="studio-meta-row">
            Preview route contract: <code>/preview/:screenId</code>
          </p>
          <div className="studio-link-row">
            <Link to="/" className="studio-link">
              기본 프리뷰 라우트로 이동
            </Link>
          </div>
        </header>

        <div className="studio-layout">
          <section className="studio-panel">
            <h2 className="studio-panel-title">프로젝트 설정</h2>
            <form className="studio-form" onSubmit={handleRunStart}>
              <label className="studio-field" htmlFor="sourceXmlPath">
                <span className="studio-field-label">원본 XML 경로</span>
                <input
                  id="sourceXmlPath"
                  className="studio-input"
                  type="text"
                  value={formConfig.sourceXmlPath}
                  onChange={(event) => handleInputChange("sourceXmlPath", event.target.value)}
                  placeholder="예: data/sample.xml"
                />
              </label>

              <label className="studio-field" htmlFor="outputPath">
                <span className="studio-field-label">결과 경로</span>
                <input
                  id="outputPath"
                  className="studio-input"
                  type="text"
                  value={formConfig.outputPath}
                  onChange={(event) => handleInputChange("outputPath", event.target.value)}
                  placeholder="예: out/studio"
                />
              </label>

              <label className="studio-field" htmlFor="previewHostPath">
                <span className="studio-field-label">preview-host 경로</span>
                <input
                  id="previewHostPath"
                  className="studio-input"
                  type="text"
                  value={formConfig.previewHostPath}
                  onChange={(event) => handleInputChange("previewHostPath", event.target.value)}
                  placeholder="예: preview-host"
                />
              </label>

              <fieldset className="studio-render-mode-group">
                <legend className="studio-field-label">렌더 모드</legend>
                <label className="studio-render-option" htmlFor="renderModeStrict">
                  <input
                    id="renderModeStrict"
                    type="radio"
                    name="renderMode"
                    checked={formConfig.renderMode === "strict"}
                    onChange={() => handleRenderModeChange("strict")}
                  />
                  <span>strict</span>
                </label>
                <label className="studio-render-option" htmlFor="renderModeMui">
                  <input
                    id="renderModeMui"
                    type="radio"
                    name="renderMode"
                    checked={formConfig.renderMode === "mui"}
                    onChange={() => handleRenderModeChange("mui")}
                  />
                  <span>mui</span>
                </label>
                <label className="studio-render-option" htmlFor="renderModeAuto">
                  <input
                    id="renderModeAuto"
                    type="radio"
                    name="renderMode"
                    checked={formConfig.renderMode === "auto"}
                    onChange={() => handleRenderModeChange("auto")}
                  />
                  <span>auto</span>
                </label>
              </fieldset>

              <div className="studio-actions">
                <button
                  type="submit"
                  className="studio-button studio-button-primary"
                  disabled={runState === "running"}
                >
                  변환 시작
                </button>
                <button
                  type="button"
                  className="studio-button studio-button-secondary"
                  onClick={handleCancel}
                  disabled={runState !== "running"}
                >
                  실행 취소
                </button>
              </div>
            </form>
          </section>

          <section className="studio-panel">
            <h2 className="studio-panel-title">실행 상태</h2>
            <div className="studio-status-card">
              <span className={`studio-status-badge studio-status-${runState}`}>
                {STATE_LABEL[runState]}
              </span>
              <p className="studio-status-message">{statusMessage}</p>
              <dl className="studio-status-meta">
                <div>
                  <dt>Adapter</dt>
                  <dd>{adapterName}</dd>
                </div>
                <div>
                  <dt>Started</dt>
                  <dd>{startedAt ? formatClock(startedAt) : "-"}</dd>
                </div>
                <div>
                  <dt>Ended</dt>
                  <dd>{endedAt ? formatClock(endedAt) : "-"}</dd>
                </div>
                <div>
                  <dt>Report 상태</dt>
                  <dd>{reportState ? STATE_LABEL[reportState] : "-"}</dd>
                </div>
              </dl>
            </div>
          </section>

          <section className="studio-panel studio-panel-wide">
            <h2 className="studio-panel-title">실시간 로그</h2>
            <div className="studio-log-panel">
              {logs.length === 0 ? (
                <p className="studio-empty">로그가 아직 없습니다.</p>
              ) : (
                <ul className="studio-log-list">
                  {logs.map((entry) => (
                    <li
                      key={entry.id}
                      className={`studio-log-line studio-log-${entry.level}`}
                    >
                      <span className="studio-log-time">[{formatClock(entry.timestamp)}]</span>{" "}
                      <span>{entry.message}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>

          <section className="studio-panel studio-panel-wide">
            <h2 className="studio-panel-title">리포트 요약</h2>
            {report ? (
              <>
                <div className="studio-report-cards">
                  <article className="studio-report-card">
                    <h3>Markdown Report</h3>
                    <p className="studio-report-meta">
                      path: <code>{report.markdownReport.path ?? "(없음)"}</code>
                    </p>
                    <div className="studio-inline-actions">
                      <button
                        type="button"
                        className="studio-button studio-button-secondary"
                        onClick={() => setActiveTab("markdown")}
                        disabled={!markdownBody}
                      >
                        원문 탭 보기
                      </button>
                      {markdownDataUrl ? (
                        <a
                          className="studio-link"
                          href={markdownDataUrl}
                          target="_blank"
                          rel="noreferrer"
                        >
                          새 탭 열기
                        </a>
                      ) : null}
                    </div>
                  </article>

                  <article className="studio-report-card">
                    <h3>JSON Report</h3>
                    <p className="studio-report-meta">
                      path: <code>{report.jsonReport.path ?? "(없음)"}</code>
                    </p>
                    <div className="studio-inline-actions">
                      <button
                        type="button"
                        className="studio-button studio-button-secondary"
                        onClick={() => setActiveTab("json")}
                        disabled={!jsonBody}
                      >
                        원문 탭 보기
                      </button>
                      {jsonDataUrl ? (
                        <a
                          className="studio-link"
                          href={jsonDataUrl}
                          target="_blank"
                          rel="noreferrer"
                        >
                          새 탭 열기
                        </a>
                      ) : null}
                    </div>
                  </article>
                </div>

                <div className="studio-tab-row" role="tablist" aria-label="report raw view tabs">
                  <button
                    type="button"
                    role="tab"
                    aria-selected={activeTab === "summary"}
                    className={`studio-tab-button ${activeTab === "summary" ? "is-active" : ""}`}
                    onClick={() => setActiveTab("summary")}
                  >
                    Summary
                  </button>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={activeTab === "markdown"}
                    className={`studio-tab-button ${activeTab === "markdown" ? "is-active" : ""}`}
                    onClick={() => setActiveTab("markdown")}
                    disabled={!markdownBody}
                  >
                    Markdown Raw
                  </button>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={activeTab === "json"}
                    className={`studio-tab-button ${activeTab === "json" ? "is-active" : ""}`}
                    onClick={() => setActiveTab("json")}
                    disabled={!jsonBody}
                  >
                    JSON Raw
                  </button>
                </div>

                <div className="studio-tab-panel" role="tabpanel">
                  {activeTab === "summary" ? (
                    <>
                      <p className="studio-report-verdict">
                        Verdict: <strong>{report.verdict}</strong> / Duration: {report.durationMs}ms
                      </p>
                      <table className="studio-stage-table">
                        <thead>
                          <tr>
                            <th scope="col">Stage</th>
                            <th scope="col">Status</th>
                            <th scope="col">Warnings</th>
                            <th scope="col">Errors</th>
                          </tr>
                        </thead>
                        <tbody>
                          {stageRows.length === 0 ? (
                            <tr>
                              <td colSpan={4}>stage 정보가 없습니다.</td>
                            </tr>
                          ) : (
                            stageRows.map((stage) => (
                              <tr key={stage.stage}>
                                <td>{stage.stage}</td>
                                <td>{stage.status}</td>
                                <td>{stage.warnings}</td>
                                <td>{stage.errors}</td>
                              </tr>
                            ))
                          )}
                        </tbody>
                      </table>
                    </>
                  ) : null}
                  {activeTab === "markdown" ? (
                    <pre className="studio-raw-block">{markdownBody}</pre>
                  ) : null}
                  {activeTab === "json" ? (
                    <pre className="studio-raw-block">{jsonBody}</pre>
                  ) : null}
                </div>
              </>
            ) : (
              <p className="studio-empty">리포트가 아직 없습니다. 변환을 실행해주세요.</p>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}
