// --------------------------------------------------------------------------
// frontend/src/App.js — City Medical Clinic Chatbot
//
// Main React component for the chatbot frontend. Features:
// - Multi-session chat with WebSocket streaming
// - Voice input via browser MediaRecorder + ASR service
// - TTS audio playback for AI responses
// - FAQ suggested prompt chips when chat is empty
// - Message timestamps, response times, and copy buttons
// - Mobile responsive sidebar
// --------------------------------------------------------------------------

import { useState, useEffect, useRef, useCallback } from "react";
import "./App.css";
import ReactMarkdown from "react-markdown";

// ---------------------------------------------------------------------------
// Configuration — API endpoints
// These default to localhost for local Docker development.
// For Vercel deployment, set REACT_APP_API_URL environment variable.
// ---------------------------------------------------------------------------
const API_URL = process.env.REACT_APP_API_URL || "http://localhost:8000";
const WS_URL = process.env.REACT_APP_WS_URL || "ws://localhost:8000";

let chatCounter = 1;

// ---------------------------------------------------------------------------
// FAQ suggested prompts — shown when chat is empty
// ---------------------------------------------------------------------------
const FAQ_PROMPTS = [
  {
    icon: "📅",
    text: "I'd like to book an appointment with a doctor",
  },
  {
    icon: "🏥",
    text: "What are the clinic hours and which doctors are available?",
  },
  {
    icon: "🤒",
    text: "I've been having headaches and fever for two days",
  },
  {
    icon: "👶",
    text: "I need to schedule a checkup for my child",
  },
];

function App() {
  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------
  const [chats, setChats] = useState([]); // [{id, sessionId, title, messages}]
  const [activeChatId, setActiveChatId] = useState(null);
  const [input, setInput] = useState("");
  const [isConnected, setIsConnected] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Voice state
  const [isRecording, setIsRecording] = useState(false);
  const [voiceState, setVoiceState] = useState(null); // null | "recording" | "processing" | "speaking"
  const [isMuted, setIsMuted] = useState(false);
  const [copiedId, setCopiedId] = useState(null);

  // Refs
  const wsRef = useRef(null);
  const bottomRef = useRef(null);
  const inputRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const streamStartRef = useRef(null);

  // ---------------------------------------------------------------------------
  // WebSocket connection
  // ---------------------------------------------------------------------------
  const connectWebSocket = useCallback((sessionId, chatId) => {
    if (wsRef.current) wsRef.current.close();
    const ws = new WebSocket(`${WS_URL}/ws/chat/${sessionId}`);
    ws.onopen = () => setIsConnected(true);
    ws.onclose = () => setIsConnected(false);
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.done) {
        setIsStreaming(false);
        // Mark streaming done and calculate response time
        setChats((prev) =>
          prev.map((c) => {
            if (c.id !== chatId) return c;
            const msgs = [...c.messages];
            const last = msgs[msgs.length - 1];
            if (last?.role === "assistant") {
              const responseTime = streamStartRef.current
                ? ((Date.now() - streamStartRef.current) / 1000).toFixed(1)
                : null;
              msgs[msgs.length - 1] = {
                ...last,
                streaming: false,
                responseTime: responseTime ? `${responseTime}s` : null,
              };
            }
            return { ...c, messages: msgs };
          })
        );
        return;
      }
      if (data.token) {
        setChats((prev) =>
          prev.map((c) => {
            if (c.id !== chatId) return c;
            const msgs = [...c.messages];
            const last = msgs[msgs.length - 1];
            if (last?.role === "assistant" && last.streaming) {
              msgs[msgs.length - 1] = {
                ...last,
                content: last.content + data.token,
              };
            }
            return { ...c, messages: msgs };
          })
        );
      }
    };
    wsRef.current = ws;
  }, []);

  // ---------------------------------------------------------------------------
  // Session management
  // ---------------------------------------------------------------------------
  const createNewChat = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/session`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const data = await res.json();
      const chatId = `chat-${Date.now()}`;
      const welcomeMsg = {
        role: "assistant",
        content:
          "Hello! I'm Sara, the receptionist at City Medical Clinic. How can I help you today? 😊",
        streaming: false,
        timestamp: new Date().toISOString(),
      };
      const newChat = {
        id: chatId,
        sessionId: data.session_id,
        title: `Chat ${chatCounter++}`,
        messages: [welcomeMsg],
      };
      setChats((prev) => [newChat, ...prev]);
      setActiveChatId(chatId);
      setInput("");
      setIsStreaming(false);
      setSidebarOpen(false);
      connectWebSocket(data.session_id, chatId);
    } catch (err) {
      console.error("Failed to create session:", err);
    }
  }, [connectWebSocket]);

  // Init with one chat
  useEffect(() => {
    createNewChat();
    return () => wsRef.current?.close();
  }, [createNewChat]);

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chats, activeChatId]);

  const switchChat = (chat) => {
    if (isStreaming) return;
    setActiveChatId(chat.id);
    setInput("");
    setSidebarOpen(false);
    connectWebSocket(chat.sessionId, chat.id);
  };

  const deleteChat = async (e, chat) => {
    e.stopPropagation();
    try {
      await fetch(`${API_URL}/session/${chat.sessionId}`, { method: "DELETE" });
    } catch (err) {
      console.error("Failed to delete session:", err);
    }
    setChats((prev) => {
      const remaining = prev.filter((c) => c.id !== chat.id);
      if (activeChatId === chat.id && remaining.length > 0) {
        const next = remaining[0];
        setActiveChatId(next.id);
        connectWebSocket(next.sessionId, next.id);
      } else if (remaining.length === 0) {
        setActiveChatId(null);
      }
      return remaining;
    });
  };

  // ---------------------------------------------------------------------------
  // Send text message
  // ---------------------------------------------------------------------------
  const sendMessage = (messageText) => {
    const text = messageText || input;
    if (!text.trim() || !isConnected || isStreaming) return;

    const userMsg = {
      role: "user",
      content: text.trim(),
      streaming: false,
      timestamp: new Date().toISOString(),
    };
    const assistantMsg = {
      role: "assistant",
      content: "",
      streaming: true,
      timestamp: new Date().toISOString(),
    };

    streamStartRef.current = Date.now();

    setChats((prev) =>
      prev.map((c) => {
        if (c.id !== activeChatId) return c;
        const isFirst =
          c.messages.filter((m) => m.role === "user").length === 0;
        return {
          ...c,
          title: isFirst
            ? text.trim().slice(0, 30) + (text.length > 30 ? "..." : "")
            : c.title,
          messages: [...c.messages, userMsg, assistantMsg],
        };
      })
    );

    setIsStreaming(true);
    wsRef.current.send(JSON.stringify({ message: text.trim() }));
    setInput("");
    inputRef.current?.focus();
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  // ---------------------------------------------------------------------------
  // FAQ chip click — populate input and send
  // ---------------------------------------------------------------------------
  const handleFaqClick = (promptText) => {
    setInput(promptText);
    // Small delay to show the text in input before sending
    setTimeout(() => sendMessage(promptText), 100);
  };

  // ---------------------------------------------------------------------------
  // Copy message to clipboard
  // ---------------------------------------------------------------------------
  const copyMessage = async (content, msgIndex) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedId(msgIndex);
      setTimeout(() => setCopiedId(null), 2000);
    } catch (err) {
      console.error("Copy failed:", err);
    }
  };

  // ---------------------------------------------------------------------------
  // Voice recording — uses MediaRecorder API to capture mic audio
  // ---------------------------------------------------------------------------
  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
          ? "audio/webm;codecs=opus"
          : "audio/webm",
      });

      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        // Stop all tracks to release mic
        stream.getTracks().forEach((track) => track.stop());

        const audioBlob = new Blob(audioChunksRef.current, {
          type: "audio/webm",
        });
        await processVoiceInput(audioBlob);
      };

      mediaRecorderRef.current = mediaRecorder;
      mediaRecorder.start();
      setIsRecording(true);
      setVoiceState("recording");
    } catch (err) {
      console.error("Mic access denied:", err);
      alert(
        "Microphone access is required for voice input. Please allow mic access and try again."
      );
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const toggleRecording = () => {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  // ---------------------------------------------------------------------------
  // Process voice input — send to ASR, get transcription, then send as chat
  // ---------------------------------------------------------------------------
  const processVoiceInput = async (audioBlob) => {
    setVoiceState("processing");

    try {
      // Send audio to ASR endpoint for transcription
      const formData = new FormData();
      formData.append("file", audioBlob, "recording.webm");

      const response = await fetch(`${API_URL}/api/voice/transcribe`, {
        method: "POST",
        body: formData,
      });

      if (response.status === 503) {
        alert(
          "Voice service is at capacity. Please try again in a few seconds."
        );
        setVoiceState(null);
        return;
      }

      if (!response.ok) {
        throw new Error(`ASR failed: ${response.status}`);
      }

      const result = await response.json();
      const transcribedText = result.text?.trim();

      if (!transcribedText) {
        alert("Could not understand the audio. Please try again.");
        setVoiceState(null);
        return;
      }

      // Show transcribed text in input so user can see/edit it
      setInput(transcribedText);
      setVoiceState(null);

      // Auto-send after showing briefly
      setTimeout(() => {
        sendMessage(transcribedText);
      }, 500);
    } catch (err) {
      console.error("Voice processing error:", err);
      setVoiceState(null);
      alert("Voice processing failed. Make sure the backend services are running.");
    }
  };

  // ---------------------------------------------------------------------------
  // TTS playback — synthesize AI response audio and play it
  // ---------------------------------------------------------------------------
  const playTTS = async (text) => {
    if (isMuted || !text.trim()) return;

    setVoiceState("speaking");
    try {
      const response = await fetch(`${API_URL}/api/voice/synthesize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: text.slice(0, 500) }),
      });

      if (!response.ok) {
        console.warn("TTS unavailable:", response.status);
        setVoiceState(null);
        return;
      }

      const audioBlob = await response.blob();
      const audioUrl = URL.createObjectURL(audioBlob);
      const audio = new Audio(audioUrl);

      audio.onended = () => {
        setVoiceState(null);
        URL.revokeObjectURL(audioUrl);
      };

      audio.onerror = () => {
        setVoiceState(null);
        URL.revokeObjectURL(audioUrl);
      };

      await audio.play();
    } catch (err) {
      console.warn("TTS playback failed (service may not be running):", err);
      setVoiceState(null);
    }
  };

  // Auto-play TTS when a non-streaming assistant message arrives
  // Only trigger for the most recent message that just finished streaming
  useEffect(() => {
    if (isMuted) return;
    const activeChat = chats.find((c) => c.id === activeChatId);
    if (!activeChat) return;

    const msgs = activeChat.messages;
    const lastMsg = msgs[msgs.length - 1];

    // Play TTS only when streaming just finished (streaming was true, now false)
    // and the message has actual content
    if (
      lastMsg?.role === "assistant" &&
      lastMsg.streaming === false &&
      lastMsg.content &&
      lastMsg.responseTime // This is set when streaming completes
    ) {
      // Only play if service is likely available (don't spam errors)
      playTTS(lastMsg.content);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isStreaming]);

  // ---------------------------------------------------------------------------
  // Format timestamp
  // ---------------------------------------------------------------------------
  const formatTime = (isoString) => {
    if (!isoString) return "";
    const d = new Date(isoString);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  };

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  const activeChat = chats.find((c) => c.id === activeChatId);
  const hasUserMessages =
    activeChat?.messages.filter((m) => m.role === "user").length > 0;

  return (
    <div className="app">
      {/* Mobile sidebar overlay */}
      <div
        className={`sidebar-overlay ${sidebarOpen ? "visible" : ""}`}
        onClick={() => setSidebarOpen(false)}
      />

      {/* ── Sidebar ── */}
      <aside className={`sidebar ${sidebarOpen ? "open" : ""}`}>
        <div className="sidebar-top">
          <div className="clinic-brand">
            <span className="brand-icon">⚕️</span>
            <span className="brand-name">City Medical Clinic</span>
          </div>
          <button className="new-chat-btn" onClick={createNewChat}>
            <span>+</span> New Chat
          </button>
        </div>

        <div className="chat-list">
          {chats.length === 0 && <p className="no-chats">No chats yet</p>}
          {chats.map((chat) => (
            <div
              key={chat.id}
              className={`chat-item ${
                chat.id === activeChatId ? "active" : ""
              }`}
              onClick={() => switchChat(chat)}
            >
              <span className="chat-icon">💬</span>
              <span className="chat-title">{chat.title}</span>
              <button
                className="delete-chat-btn"
                onClick={(e) => deleteChat(e, chat)}
                title="Delete chat"
              >
                ×
              </button>
            </div>
          ))}
        </div>

        <div className="sidebar-bottom">
          <div className="status-indicator">
            <span className={`dot ${isConnected ? "online" : "offline"}`} />
            <span>{isConnected ? "Connected" : "Disconnected"}</span>
          </div>
          {activeChat && (
            <div className="session-info">
              Session: {activeChat.sessionId.slice(0, 8)}...
            </div>
          )}
        </div>
      </aside>

      {/* ── Main Chat ── */}
      <main className="chat-main">
        <div className="chat-header">
          <div className="chat-header-left">
            <button
              className="mobile-toggle"
              onClick={() => setSidebarOpen(!sidebarOpen)}
            >
              ☰
            </button>
            <div className="header-avatar">S</div>
            <div className="header-info">
              <h1>Sara</h1>
              <span className="subtitle">Medical Receptionist — City Clinic</span>
            </div>
          </div>
          <div className="header-status">
            <span className={`dot ${isConnected ? "online" : "offline"}`} />
            <span>{isConnected ? "Online" : "Offline"}</span>
          </div>
        </div>

        {/* FAQ chips when no user messages yet */}
        {!hasUserMessages && activeChat ? (
          <div className="faq-container">
            <div className="faq-hero">
              <div className="faq-hero-icon">👋</div>
              <h2>How can I help you today?</h2>
              <p>
                I'm Sara, your clinic receptionist. I can help with
                appointments, clinic info, and directing you to the right
                doctor.
              </p>
            </div>
            <div className="faq-chips">
              {FAQ_PROMPTS.map((faq, i) => (
                <button
                  key={i}
                  className="faq-chip"
                  onClick={() => handleFaqClick(faq.text)}
                  disabled={!isConnected || isStreaming}
                >
                  <span className="faq-chip-icon">{faq.icon}</span>
                  <span className="faq-chip-text">{faq.text}</span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="messages-container">
            {activeChat?.messages.map((msg, i) => (
              <div key={i} className={`message-row ${msg.role}`}>
                {msg.role === "assistant" && (
                  <div className="avatar assistant-avatar">S</div>
                )}
                <div className="message-content">
                  <div className={`bubble ${msg.role}`}>
                    {msg.role === "assistant" ? (
                      <>
                        <ReactMarkdown>{msg.content}</ReactMarkdown>
                        {msg.streaming && msg.content === "" && (
                          <span className="typing-dots">
                            <span></span>
                            <span></span>
                            <span></span>
                          </span>
                        )}
                      </>
                    ) : (
                      msg.content
                    )}
                  </div>
                  <div className="message-meta">
                    <span className="message-timestamp">
                      {formatTime(msg.timestamp)}
                    </span>
                    {msg.role === "assistant" && msg.responseTime && (
                      <span className="response-time">
                        ⚡ {msg.responseTime}
                      </span>
                    )}
                    {msg.role === "assistant" &&
                      !msg.streaming &&
                      msg.content && (
                        <button
                          className={`copy-btn ${
                            copiedId === i ? "copied" : ""
                          }`}
                          onClick={() => copyMessage(msg.content, i)}
                          title="Copy message"
                        >
                          {copiedId === i ? "✓ Copied" : "📋 Copy"}
                        </button>
                      )}
                  </div>
                </div>
                {msg.role === "user" && (
                  <div className="avatar user-avatar">U</div>
                )}
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        )}

        {/* ── Input Area ── */}
        <div className="input-area">
          {/* Voice state indicator */}
          {voiceState && (
            <div className={`voice-status ${voiceState}`}>
              {voiceState === "recording" && "🔴 Recording... Click mic to stop"}
              {voiceState === "processing" && "⏳ Processing your voice..."}
              {voiceState === "speaking" && "🔊 Playing response..."}
            </div>
          )}

          <div className="input-wrapper">
            {/* Microphone button */}
            <button
              className={`mic-btn ${isRecording ? "recording" : ""}`}
              onClick={toggleRecording}
              disabled={!isConnected || isStreaming || voiceState === "processing"}
              title={isRecording ? "Stop recording" : "Start voice input"}
            >
              {isRecording ? "⏹" : "🎤"}
            </button>

            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Message Sara..."
              rows={1}
              disabled={!isConnected || isStreaming || !activeChat}
            />

            {/* Mute/unmute TTS toggle */}
            <button
              className={`mute-btn ${isMuted ? "muted" : ""}`}
              onClick={() => setIsMuted(!isMuted)}
              title={isMuted ? "Unmute TTS" : "Mute TTS"}
            >
              {isMuted ? "🔇" : "🔊"}
            </button>

            {/* Send button */}
            <button
              className="send-btn"
              onClick={() => sendMessage()}
              disabled={!input.trim() || !isConnected || isStreaming}
            >
              ↑
            </button>
          </div>

          <p className="disclaimer">
            City Medical Clinic · Not for medical emergencies · Call 911 if urgent
          </p>
        </div>
      </main>
    </div>
  );
}

export default App;