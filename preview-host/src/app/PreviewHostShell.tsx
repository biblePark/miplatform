import type { ReactNode } from "react";

interface PreviewHostShellProps {
  title: string;
  subtitle: string;
  children: ReactNode;
}

export function PreviewHostShell({
  title,
  subtitle,
  children,
}: PreviewHostShellProps) {
  return (
    <main
      style={{
        minHeight: "100vh",
        padding: "32px 24px",
        display: "grid",
        placeItems: "start center",
      }}
    >
      <div
        style={{
          width: "min(1100px, 100%)",
          background: "#ffffff",
          border: "1px solid #d7e1f2",
          borderRadius: 12,
          boxShadow: "0 8px 24px rgba(20, 35, 60, 0.08)",
        }}
      >
        <header
          style={{
            padding: "20px 24px",
            borderBottom: "1px solid #d7e1f2",
            background: "linear-gradient(135deg, #f0f6ff 0%, #f8fbff 100%)",
          }}
        >
          <h1 style={{ margin: 0, fontSize: 22 }}>{title}</h1>
          <p style={{ margin: "8px 0 0", color: "#4f607f" }}>{subtitle}</p>
          <p style={{ margin: "12px 0 0" }}>
            Route contract: <code>/preview/:screenId</code>
          </p>
          <a href="/">Go to default preview route</a>
        </header>
        <section style={{ padding: "20px 24px" }}>{children}</section>
      </div>
    </main>
  );
}
