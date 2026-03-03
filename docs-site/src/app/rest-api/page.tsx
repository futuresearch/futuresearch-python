"use client";

import { ApiReferenceReact } from "@scalar/api-reference-react";
import "@scalar/api-reference-react/style.css";
import spec from "../../../public/openapi.json";

export default function RestApiPage() {
  return (
    <div className="rest-api-page">
      <ApiReferenceReact
        configuration={{
          content: spec,
          layout: "modern",
          theme: "default",
          darkMode: true,
          hideDarkModeToggle: true,
          withDefaultFonts: false,
          customCss: `
            .scalar-app {
              font-family: var(--font-inter), ui-sans-serif, system-ui, sans-serif;
            }
            .scalar-app code, .scalar-app pre {
              font-family: var(--font-jetbrains), ui-monospace, monospace;
            }
          `,
        }}
      />
    </div>
  );
}
