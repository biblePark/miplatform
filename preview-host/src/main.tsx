import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { PreviewApp } from "./app/PreviewApp";
import "./styles.css";

const container = document.getElementById("root");
if (!container) {
  throw new Error("Preview host root container (#root) was not found.");
}

createRoot(container).render(
  <StrictMode>
    <PreviewApp />
  </StrictMode>
);
