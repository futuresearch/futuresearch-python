"use client";

import { useState, useEffect, createContext, useContext, ReactNode } from "react";

type Agent = "claude-ai" | "claude-code" | "claude-cowork" | "python-sdk" | "codex" | "gemini" | "cursor";
type IntegrationType = "pip" | "uv" | "skills" | "mcp" | "plugin";

interface TabContextValue {
  selectedAgent: Agent;
  selectedType: IntegrationType;
  isActive: (agent: Agent, type: IntegrationType) => boolean;
}

const TabContext = createContext<TabContextValue | null>(null);

const AGENTS: { id: Agent; label: string }[] = [
  { id: "claude-ai", label: "Claude.ai" },
  { id: "claude-code", label: "Claude Code" },
  { id: "claude-cowork", label: "Claude Cowork" },
  { id: "python-sdk", label: "Python SDK" },
  { id: "codex", label: "Codex" },
  { id: "gemini", label: "Gemini" },
  { id: "cursor", label: "Cursor" },
];

const TYPES: { id: IntegrationType; label: string }[] = [
  { id: "pip", label: "pip" },
  { id: "uv", label: "uv" },
  { id: "skills", label: "Skills" },
  { id: "mcp", label: "MCP" },
  { id: "plugin", label: "Plugin" },
];

// Which integration types are available for each agent
const AGENT_TYPES: Record<Agent, IntegrationType[]> = {
  "claude-ai": ["mcp"],
  "claude-code": ["mcp", "plugin"],
  "claude-cowork": ["mcp"],
  "python-sdk": ["pip", "uv"],
  "codex": ["skills", "mcp"],
  "gemini": ["skills", "mcp", "plugin"],
  "cursor": ["skills", "mcp"],
};

// Hash format: #tab-{agent}-{type}
function parseHash(hash: string): { agent: Agent; type: IntegrationType } | null {
  const match = hash.match(/^#tab-([a-z-]+)-([a-z]+)$/);
  if (!match) return null;
  const agent = match[1] as Agent;
  const type = match[2] as IntegrationType;
  if (!AGENT_TYPES[agent]?.includes(type)) return null;
  return { agent, type };
}

function buildHash(agent: Agent, type: IntegrationType): string {
  return `#tab-${agent}-${type}`;
}

interface InstallationTabsProps {
  children: ReactNode;
}

export function InstallationTabs({ children }: InstallationTabsProps) {
  const [selectedAgent, setSelectedAgent] = useState<Agent>("claude-ai");
  const [selectedType, setSelectedType] = useState<IntegrationType>("mcp");

  // Read hash on mount (client-side only, after hydration)
  useEffect(() => {
    const parsed = parseHash(window.location.hash);
    if (parsed) {
      setSelectedAgent(parsed.agent);
      setSelectedType(parsed.type);
    }
  }, []);

  // Get available types for selected agent
  const availableTypes = AGENT_TYPES[selectedAgent];

  // If current type isn't available for new agent, switch to first available
  const effectiveType = availableTypes.includes(selectedType)
    ? selectedType
    : availableTypes[0];

  const updateHash = (agent: Agent, type: IntegrationType) => {
    window.history.replaceState(null, "", buildHash(agent, type));
  };

  const handleAgentChange = (agent: Agent) => {
    const newType = AGENT_TYPES[agent].includes(selectedType)
      ? selectedType
      : AGENT_TYPES[agent][0];
    setSelectedAgent(agent);
    setSelectedType(newType);
    updateHash(agent, newType);
  };

  const handleTypeChange = (type: IntegrationType) => {
    setSelectedType(type);
    updateHash(selectedAgent, type);
  };

  const isActive = (agent: Agent, type: IntegrationType) => {
    return selectedAgent === agent && effectiveType === type;
  };

  return (
    <TabContext.Provider value={{ selectedAgent, selectedType: effectiveType, isActive }}>
      <div className="installation-tabs">
        <div className="tab-selectors">
          <div className="tab-selector-row">
            <span className="tab-selector-label">Platform</span>
            <div className="tab-selector-options">
              {AGENTS.map((agent) => (
                <button
                  key={agent.id}
                  className={`tab-option ${selectedAgent === agent.id ? "active" : ""}`}
                  onClick={() => handleAgentChange(agent.id)}
                >
                  {agent.label}
                </button>
              ))}
            </div>
          </div>
          <div className="tab-selector-row">
            <span className="tab-selector-label">Method</span>
            <div className="tab-selector-options">
              {TYPES.map((type) => {
                const isAvailable = availableTypes.includes(type.id);
                return (
                  <button
                    key={type.id}
                    className={`tab-option ${effectiveType === type.id ? "active" : ""} ${!isAvailable ? "disabled" : ""}`}
                    onClick={() => isAvailable && handleTypeChange(type.id)}
                    disabled={!isAvailable}
                    title={!isAvailable ? `${type.label} not available for ${AGENTS.find(a => a.id === selectedAgent)?.label}` : undefined}
                  >
                    {type.label}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
        <div className="tab-contents">
          {children}
        </div>
      </div>
    </TabContext.Provider>
  );
}

interface TabContentProps {
  agent: Agent;
  type: IntegrationType;
  children: ReactNode;
}

export function TabContent({ agent, type, children }: TabContentProps) {
  const context = useContext(TabContext);

  // During SSR or if no context, show all content (for no-JS readers)
  const isActive = context?.isActive(agent, type) ?? true;

  // Get readable labels for the heading
  const agentLabel = AGENTS.find(a => a.id === agent)?.label ?? agent;
  const typeLabel = TYPES.find(t => t.id === type)?.label ?? type;
  const heading = `${agentLabel} with ${typeLabel}`;

  return (
    <div
      className={`tab-content ${isActive ? "active" : ""}`}
      data-agent={agent}
      data-type={type}
    >
      <h3 className="tab-content-heading">{heading}</h3>
      {children}
    </div>
  );
}
