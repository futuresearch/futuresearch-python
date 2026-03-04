"use client";

import { useState, createContext, useContext, ReactNode } from "react";

type GuideTab = "app" | "claude-ai" | "claude-code" | "python";

const GuideTabContext = createContext<GuideTab | null>(null);

const TABS: { id: GuideTab; label: string }[] = [
  { id: "app", label: "App" },
  { id: "claude-ai", label: "Claude.ai / Cowork" },
  { id: "claude-code", label: "Claude Code" },
  { id: "python", label: "Python SDK" },
];

interface GuideTabsProps {
  children: ReactNode;
}

export function GuideTabs({ children }: GuideTabsProps) {
  const [selected, setSelected] = useState<GuideTab>("app");

  return (
    <GuideTabContext.Provider value={selected}>
      <div className="guide-tabs">
        <div className="guide-tab-selector">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              className={`tab-option ${selected === tab.id ? "active" : ""}`}
              onClick={() => setSelected(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <div className="tab-contents">
          {children}
        </div>
      </div>
    </GuideTabContext.Provider>
  );
}

interface GuideTabContentProps {
  tab: GuideTab;
  children: ReactNode;
}

export function GuideTabContent({ tab, children }: GuideTabContentProps) {
  const selected = useContext(GuideTabContext);

  // During SSR or no context, show all content (static fallback)
  const isActive = selected === null || selected === tab;

  return (
    <div
      className={`tab-content ${isActive ? "active" : ""}`}
      data-tab={tab}
    >
      {children}
    </div>
  );
}
