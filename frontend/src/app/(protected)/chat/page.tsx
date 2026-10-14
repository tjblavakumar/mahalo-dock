"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { useProjects } from "@/contexts/ProjectContext";
import { useConnections } from "@/contexts/ConnectionsContext";
import { useRequiredConnections } from "@/hooks/useRequiredConnections";
import { buildSuggestions, type IntegrationType } from "@/lib/chatSuggestions";
import { api } from "@/services/api";
import ChatInput from "@/components/chat/ChatInput";
import ChatMessage from "@/components/chat/ChatMessage";
import ProposalCard from "@/components/chat/ProposalCard";
import ContextPanel from "@/components/chat/ContextPanel";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  systemsQueried?: string[];
  proposal?: Proposal | null;
}

interface Proposal {
  action: string;
  system: string;
  params: Record<string, unknown>;
  description: string;
}

interface ActionResult {
  success: boolean;
  message: string;
}

interface ChatApiResponse {
  response: string;
  proposal: Proposal | null;
  systems_queried: string[];
  session_id: string;
}

export default function ChatPage() {
  const { user } = useAuth();
  const { activeProject, selectedProjects } = useProjects();
  const { integrations } = useConnections();
  const { isConfigured, loading: connectionsLoading } = useRequiredConnections();
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [actionResults, setActionResults] = useState<Record<string, ActionResult>>({});
  const [approvingId, setApprovingId] = useState<string | null>(null);
  // Optional LLM-generated suggestions from "Generate more". Tagged with the
  // context signature they were generated for, so they're automatically
  // discarded when the role/project/connections change (requirement: recompute
  // from current context).
  const [llmSuggestions, setLlmSuggestions] = useState<{ signature: string; items: string[] } | null>(null);
  const [generatingSuggestions, setGeneratingSuggestions] = useState(false);
  const [contextPanel, setContextPanel] = useState<{
    isOpen: boolean;
    title: string;
    content: string;
    type: "story" | "document" | "pr";
  }>({ isOpen: false, title: "", content: "", type: "story" });

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messageIdRef = useRef(0);
  // Tracks the project scope the current session was started under, so we can
  // start a fresh session when the sidebar selection changes.
  const sessionScopeRef = useRef<number | null>(null);

  // Generates a stable, unique message id without calling impure functions
  // (like Date.now()) during render. The counter lives in a ref and is only
  // advanced from event handlers.
  const nextMessageId = useCallback((suffix?: string) => {
    messageIdRef.current += 1;
    return suffix ? `msg-${messageIdRef.current}-${suffix}` : `msg-${messageIdRef.current}`;
  }, []);

  // The chat scope follows the sidebar's project selection. When exactly one
  // project is selected we scope answers to it; with none or several selected we
  // fall back to the active project (the backend accepts a single project_id).
  const scopedProject = useMemo(() => {
    if (selectedProjects.length === 1) return selectedProjects[0];
    return activeProject;
  }, [selectedProjects, activeProject]);

  const scopedProjectId = scopedProject?.id ?? null;

  // The connection types the user has actually configured. Drives which
  // suggestions we surface (e.g. no GitHub -> no PR prompts).
  const connectedTypes = useMemo<IntegrationType[]>(
    () => integrations.map((i) => i.type),
    [integrations]
  );

  // Template-derived, context-aware starter prompts. Recomputes whenever the
  // role, scoped project, or connected systems change (no random rotation).
  const templateSuggestions = useMemo(
    () =>
      buildSuggestions({
        role: user?.role,
        project: scopedProject,
        connectedTypes,
      }),
    [user?.role, scopedProject, connectedTypes]
  );

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // A stable signature of the current suggestion context. When it changes, any
  // previously generated LLM suggestions no longer apply and we fall back to
  // the freshly recomputed template set.
  const suggestionSignature = useMemo(
    () => `${user?.role ?? "none"}:${scopedProjectId ?? "none"}:${connectedTypes.slice().sort().join(",")}`,
    [user?.role, scopedProjectId, connectedTypes]
  );

  // What we actually render: the LLM set when it matches the current context,
  // otherwise the template-derived set. No effect / setState mirroring needed.
  const displayedSuggestions = useMemo(
    () =>
      llmSuggestions && llmSuggestions.signature === suggestionSignature
        ? llmSuggestions.items
        : templateSuggestions,
    [llmSuggestions, suggestionSignature, templateSuggestions]
  );

  async function handleGenerateSuggestions() {
    setGeneratingSuggestions(true);
    const result = await api.post<{ suggestions: string[] }>("/chat/suggestions", {
      project_id: scopedProjectId,
    });
    if (result.data && result.data.suggestions.length > 0) {
      setLlmSuggestions({ signature: suggestionSignature, items: result.data.suggestions });
    }
    // On error or empty response we silently keep the current (template) set.
    setGeneratingSuggestions(false);
  }

  async function handleSend(message: string) {
    const userMsg: Message = {
      id: nextMessageId(),
      role: "user",
      content: message,
    };
    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    // If the project scope changed since this session started, begin a fresh
    // session so the answer is grounded in the current selection.
    const scopeChanged = sessionScopeRef.current !== scopedProjectId;
    const effectiveSessionId = scopeChanged ? null : sessionId;

    const result = await api.post<ChatApiResponse>("/chat", {
      message,
      session_id: effectiveSessionId,
      project_id: scopedProjectId,
    });

    if (result.data) {
      sessionScopeRef.current = scopedProjectId;
      if (!effectiveSessionId || result.data.session_id !== sessionId) {
        setSessionId(result.data.session_id);
      }

      const assistantMsg: Message = {
        id: nextMessageId("resp"),
        role: "assistant",
        content: result.data.response,
        systemsQueried: result.data.systems_queried,
        proposal: result.data.proposal,
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } else {
      const errorMsg: Message = {
        id: nextMessageId("err"),
        role: "assistant",
        content: `Sorry, I encountered an error: ${result.error}`,
      };
      setMessages((prev) => [...prev, errorMsg]);
    }
    setIsLoading(false);
  }

  async function handleApprove(msgId: string) {
    if (!sessionId) return;
    setApprovingId(msgId);

    const result = await api.post<ActionResult>("/chat/approve", {
      session_id: sessionId,
      approved: true,
    });

    if (result.data) {
      setActionResults((prev) => ({ ...prev, [msgId]: result.data! }));
    }
    setApprovingId(null);
  }

  async function handleReject(msgId: string) {
    if (!sessionId) return;
    setApprovingId(msgId);

    const result = await api.post<ActionResult>("/chat/approve", {
      session_id: sessionId,
      approved: false,
    });

    if (result.data) {
      setActionResults((prev) => ({ ...prev, [msgId]: result.data! }));
    }
    setApprovingId(null);
  }

  return (
    <div className="flex h-screen">
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <div className="border-b border-gray-200 bg-white px-6 py-4 flex items-start justify-between gap-4">
          <div>
            <h1 className="text-lg font-semibold text-gray-900">AI Assistant</h1>
            <p className="text-sm text-gray-500">
              Ask about your projects, sprints, documentation, and code
            </p>
          </div>
          {isConfigured && (
            <div className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs text-blue-800 whitespace-nowrap self-center">
              {selectedProjects.length > 1 ? (
                <span>
                  Scoped to <strong className="font-semibold">{scopedProject?.name ?? "—"}</strong>
                  {" "}
                  <span className="text-blue-400">(of {selectedProjects.length} selected)</span>
                </span>
              ) : scopedProject ? (
                <span>Scoped to <strong className="font-semibold">{scopedProject.name}</strong></span>
              ) : (
                <span className="text-gray-500">No project scope</span>
              )}
            </div>
          )}
        </div>

        {/* Messages Area */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {messages.length === 0 && !connectionsLoading && !isConfigured && (
            <div className="text-center py-16">
              <p className="text-4xl mb-4">🔗</p>
              <h2 className="text-lg font-medium text-gray-700 mb-2">
                Connections Required
              </h2>
              <p className="text-gray-500 text-sm max-w-md mx-auto">
                Please configure{" "}
                <a href="/connections" className="text-blue-600 hover:underline font-medium">
                  Jira, Confluence, and GitHub
                </a>{" "}
                on the Connections page to start chatting about your projects.
              </p>
            </div>
          )}

          {messages.length === 0 && !connectionsLoading && isConfigured && (
            <div className="text-center py-16">
              <p className="text-4xl mb-4">💬</p>
              <h2 className="text-lg font-medium text-gray-700 mb-2">
                How can I help you today?
              </h2>
              {displayedSuggestions.length > 0 && (
                <div className="max-w-lg mx-auto mt-6">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {displayedSuggestions.map((suggestion) => (
                      <button
                        key={suggestion}
                        onClick={() => handleSend(suggestion)}
                        className="text-left px-4 py-3 border border-gray-200 rounded-lg text-sm text-gray-700 hover:bg-gray-50 hover:border-gray-300 transition-colors"
                      >
                        {suggestion}
                      </button>
                    ))}
                  </div>
                  <button
                    onClick={handleGenerateSuggestions}
                    disabled={generatingSuggestions}
                    className="mt-4 inline-flex items-center gap-1.5 text-sm text-blue-600 hover:text-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    {generatingSuggestions ? (
                      <>
                        <span className="w-3.5 h-3.5 border-2 border-blue-300 border-t-blue-600 rounded-full animate-spin" />
                        Generating…
                      </>
                    ) : (
                      <>✨ Generate more</>
                    )}
                  </button>
                </div>
              )}
            </div>
          )}

          {messages.map((msg) => (
            <div key={msg.id}>
              <ChatMessage
                role={msg.role}
                content={msg.content}
                systemsQueried={msg.systemsQueried}
              />
              {msg.proposal && (
                <ProposalCard
                  proposal={msg.proposal}
                  onApprove={() => handleApprove(msg.id)}
                  onReject={() => handleReject(msg.id)}
                  isLoading={approvingId === msg.id}
                  result={actionResults[msg.id]}
                />
              )}
            </div>
          ))}

          {isLoading && (
            <div className="flex justify-start mb-4">
              <div className="bg-white border border-gray-200 rounded-lg px-4 py-3">
                <div className="flex gap-1.5">
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:0.1s]" />
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:0.2s]" />
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        <div className="border-t border-gray-200 bg-white px-6 py-4">
          <ChatInput onSend={handleSend} disabled={isLoading || (!connectionsLoading && !isConfigured)} />
        </div>
      </div>

      {/* Context Panel */}
      <ContextPanel
        isOpen={contextPanel.isOpen}
        onClose={() => setContextPanel((prev) => ({ ...prev, isOpen: false }))}
        title={contextPanel.title}
        content={contextPanel.content}
        type={contextPanel.type}
      />
    </div>
  );
}
