import { useState, useRef, useEffect } from "react";
import { Server, Send, Sparkles } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import PodPilotLogo from "./PodPilotLogo";

// Canned responses so the page feels alive without a backend wired up yet.
// Swap sendToBackend() for a real API call when ready.
const MOCK_RESPONSES = [
  {
    match: /memory/i,
    reply:
      "Based on your live cluster snapshot, the top memory wasters are: (1) ml-training-pod — requested 4Gi, using 0.3Gi, wasting ~$22/month. (2) legacy-api — requested 2Gi, using 0.1Gi, wasting ~$11/month. Recommend lowering memory requests to actual usage + 20% buffer.",
  },
  {
    match: /cpu/i,
    reply:
      "CPU looks healthy overall — no pods are over-provisioned by more than 15%. worker-3 is the closest to its limit at 82% average utilization, worth watching if traffic grows.",
  },
  {
    match: /security|port|expose/i,
    reply:
      "service/frontend is exposed on NodePort 32001 with no network policy attached — that's your one critical finding. Recommend switching to a ClusterIP + Ingress and adding a NetworkPolicy to restrict inbound traffic.",
  },
];

const DEFAULT_REPLY =
  "I've pulled the latest snapshot for that. Nothing unusual stands out yet — ask me about memory, CPU, or security and I'll dig into the specifics.";

const STARTER_PROMPTS = [
  "Which pods are wasting the most memory right now?",
  "Any critical security issues I should fix first?",
  "How's CPU utilization looking across nodes?",
];

function getMockReply(text) {
  const found = MOCK_RESPONSES.find((r) => r.match.test(text));
  return found ? found.reply : DEFAULT_REPLY;
}

function AssistantAvatar() {
  return <PodPilotLogo size={32} />;
}

function ChatBubble({ role, content }) {
  const isUser = role === "user";
  return (
    <div className={`flex items-start gap-3 ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser && <AssistantAvatar />}
      <div
        className={`max-w-[70%] rounded-2xl px-4 py-3 text-[13.5px] leading-relaxed ${isUser
          ? "rounded-tr-sm bg-[#4f6df5] text-white"
          : "rounded-tl-sm border border-[#1c1f2f] bg-[#171c2a] text-[#e7e9ee]"
          }`}
      >
        {isUser ? (
          content
        ) : (
          <div className="markdown-body">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );
}

function TypingBubble() {
  return (
    <div className="flex items-start gap-3">
      <AssistantAvatar />
      <div className="flex items-center gap-1.5 rounded-2xl rounded-tl-sm border border-[#1c1f2f] bg-[#171c2a] px-4 py-3.5">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="h-1.5 w-1.5 animate-bounce rounded-full bg-[#9099ab]"
            style={{ animationDelay: `${i * 0.15}s` }}
          />
        ))}
      </div>
    </div>
  );
}

export default function Chat({ selectedSnapshotId, hideSystemK8s }) {
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content:
        "Hi, I'm your cluster copilot. Ask me anything about cost, reliability, performance, storage, or security for this cluster.",
    },
  ]);
  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);

  const scrollRef = useRef(null);
  const textareaRef = useRef(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, isTyping]);

  async function sendMessage(text) {
    const trimmed = text.trim();
    if (!trimmed || isTyping) return;

    setMessages((prev) => [...prev, { role: "user", content: trimmed }]);
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    setIsTyping(true);

    try {
      const backendUrl = import.meta.env.VITE_API_BASE_URL || `http://${window.location.hostname}:8000`;
      const payload = { 
        question: trimmed,
        hide_system: hideSystemK8s,
        history: messages.filter(m => m.role !== "assistant" || m.content !== "Hi, I'm your cluster copilot. Ask me anything about cost, reliability, performance, storage, or security for this cluster.") // Send history excluding the initial hardcoded greeting
      };
      if (selectedSnapshotId) {
        payload.snapshot_id = selectedSnapshotId;
      }

      const response = await fetch(`${backendUrl}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error("Failed to fetch response");
      const data = await response.json();
      setMessages((prev) => [...prev, { role: "assistant", content: data.answer }]);
    } catch (error) {
      console.error("Chat error:", error);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Sorry, I couldn't connect to the backend API." },
      ]);
    } finally {
      setIsTyping(false);
    }
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  }

  function handleInputChange(e) {
    setInput(e.target.value);
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
    }
  }

  const showStarters = messages.length === 1;

  if (!selectedSnapshotId) {
    return (
      <div className="flex h-full flex-1 flex-col items-center justify-center bg-[#0d0f18]">
        <div className="flex items-center gap-2 text-[#4f6df5] mb-4">
          <div className="h-2 w-2 animate-bounce rounded-full bg-current" style={{ animationDelay: "0ms" }}></div>
          <div className="h-2 w-2 animate-bounce rounded-full bg-current" style={{ animationDelay: "150ms" }}></div>
          <div className="h-2 w-2 animate-bounce rounded-full bg-current" style={{ animationDelay: "300ms" }}></div>
        </div>
        <p className="text-[#9099ab] text-sm animate-pulse max-w-sm text-center leading-relaxed">
          <span>Processing snapshot data and running AI analysis...</span>
          <br /><br />
          <span className="text-[12px] opacity-80">(Note: generating a new snapshot might take a few minutes)</span>
        </p>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col bg-[#0d0f18]">
      {/* Message stream */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-8 py-6">
        <div className="mx-auto flex max-w-3xl flex-col gap-5">
          {messages.map((m, i) => (
            <ChatBubble key={i} role={m.role} content={m.content} />
          ))}
          {isTyping && <TypingBubble />}

          {showStarters && !isTyping && (
            <div className="mt-2 flex flex-col gap-2">
              <p className="m-0 flex items-center gap-1.5 text-[12px] font-medium text-[#9099ab]">
                <Sparkles size={13} className="text-[#4f6df5]" />
                Try asking
              </p>
              <div className="flex flex-wrap gap-2">
                {STARTER_PROMPTS.map((prompt) => (
                  <button
                    key={prompt}
                    onClick={() => sendMessage(prompt)}
                    className="rounded-full border border-[#1c1f2f] bg-[#171c2a] px-3.5 py-1.5 text-[12.5px] text-[#9099ab] transition-colors hover:border-[#2a2f45] hover:text-[#e7e9ee]"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Composer */}
      <div className="border-t border-[#1c1f2f] bg-[#0d0f18] px-8 py-5">
        <div className="mx-auto flex max-w-3xl items-end gap-3">
          <textarea
            ref={textareaRef}
            rows={1}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder="Ask anything about your cluster..."
            className="max-h-40 flex-1 resize-none rounded-xl border border-[#1c1f2f] bg-[#171c2a] px-4 py-3 text-[13.5px] text-[#e7e9ee] placeholder:text-[#9099ab] outline-none transition-colors focus:border-[#4f6df5]/50"
          />
          <button
            onClick={() => sendMessage(input)}
            disabled={!input.trim() || isTyping}
            aria-label="Send message"
            className="flex h-[46px] w-[46px] shrink-0 items-center justify-center rounded-xl bg-[#4f6df5] text-white transition enabled:hover:bg-[#4361e0] disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Send size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}