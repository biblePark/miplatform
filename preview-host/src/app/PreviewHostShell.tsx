import {
  type CSSProperties,
  type ReactNode,
  useCallback,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";

const FALLBACK_CANVAS_WIDTH = 1280;
const FALLBACK_CANVAS_HEIGHT = 900;
const CANVAS_PADDING_PX = 24;

function measureVisibleCanvasBounds(root: HTMLElement): {
  width: number;
  height: number;
} {
  const rootRect = root.getBoundingClientRect();
  let maxRight = 0;
  let maxBottom = 0;

  const widgetNodes = root.querySelectorAll<HTMLElement>(".mi-widget-shell");
  widgetNodes.forEach((node) => {
    const computed = window.getComputedStyle(node);
    if (computed.display === "none" || computed.visibility === "hidden") {
      return;
    }

    const rect = node.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) {
      return;
    }

    maxRight = Math.max(maxRight, rect.right - rootRect.left);
    maxBottom = Math.max(maxBottom, rect.bottom - rootRect.top);
  });

  return {
    width: Math.ceil(
      (maxRight > 0 ? maxRight : FALLBACK_CANVAS_WIDTH) + CANVAS_PADDING_PX,
    ),
    height: Math.ceil(
      (maxBottom > 0 ? maxBottom : FALLBACK_CANVAS_HEIGHT) + CANVAS_PADDING_PX,
    ),
  };
}

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
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const [canvasSize, setCanvasSize] = useState<{
    width: number;
    height: number;
  }>({
    width: FALLBACK_CANVAS_WIDTH,
    height: FALLBACK_CANVAS_HEIGHT,
  });

  const updateCanvasSize = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) {
      return;
    }

    const screenRoot = canvas.querySelector<HTMLElement>(".mi-generated-screen");
    if (!screenRoot) {
      return;
    }

    const measured = measureVisibleCanvasBounds(screenRoot);
    setCanvasSize((prev) => {
      if (prev.width === measured.width && prev.height === measured.height) {
        return prev;
      }
      return measured;
    });
  }, []);

  useLayoutEffect(() => {
    const rafId = window.requestAnimationFrame(updateCanvasSize);
    const timeoutId = window.setTimeout(updateCanvasSize, 120);

    const screenRoot = canvasRef.current?.querySelector<HTMLElement>(
      ".mi-generated-screen",
    );
    const resizeObserver = new ResizeObserver(() => {
      updateCanvasSize();
    });
    if (screenRoot) {
      resizeObserver.observe(screenRoot);
    }

    window.addEventListener("resize", updateCanvasSize);

    return () => {
      window.cancelAnimationFrame(rafId);
      window.clearTimeout(timeoutId);
      resizeObserver.disconnect();
      window.removeEventListener("resize", updateCanvasSize);
    };
  }, [children, updateCanvasSize]);

  const canvasStyle = useMemo<CSSProperties>(
    () => ({
      minWidth: `${canvasSize.width}px`,
      minHeight: `${canvasSize.height}px`,
    }),
    [canvasSize],
  );

  return (
    <main className="preview-host-main">
      <div className="preview-host-shell">
        <header className="preview-host-header">
          <h1 className="preview-host-title">{title}</h1>
          <p className="preview-host-subtitle">{subtitle}</p>
          <p className="preview-host-route-contract">
            Route contract: <code>/preview/:screenId</code>
          </p>
          <a href="/" className="preview-host-home-link">
            Go to default preview route
          </a>
        </header>
        <section className="preview-host-content-scroll">
          <div className="preview-host-canvas" ref={canvasRef} style={canvasStyle}>
            {children}
          </div>
        </section>
      </div>
    </main>
  );
}
