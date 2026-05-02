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
  const [recordingMode, setRecordingMode] = useState(null); // "batch" | "stream"
  const [isMuted, setIsMuted] = useState(false);
  const [copiedId, setCopiedId] = useState(null);

  // Refs
  const wsRef = useRef(null);
  const asrWsRef = useRef(null);
  const bottomRef = useRef(null);
  const inputRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const streamStartRef = useRef(null);
  const ttsBufferRef = useRef("");
  const audioQueueRef = useRef([]);
  const isPlayingAudioRef = useRef(false);
  const recognitionIntervalRef = useRef(null);
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);


  // ---------------------------------------------------------------------------
  
  const fetchAndQueueTTS = async (text) => {
    if (isMuted || !text.trim()) return;
    try {
      const response = await fetch(`${API_URL}/api/voice/synthesize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (response.ok) {
        const audioBlob = await response.blob();
        audioQueueRef.current.push(audioBlob);
        playNextAudio();
      }
    } catch (err) {
      console.warn("TTS fetch failed:", err);
    }
  };

  const playNextAudio = () => {
    if (isPlayingAudioRef.current || audioQueueRef.current.length === 0) return;
    isPlayingAudioRef.current = true;
    setVoiceState("speaking");
    
    const audioBlob = audioQueueRef.current.shift();
    const audioUrl = URL.createObjectURL(audioBlob);
    const audio = new Audio(audioUrl);
    
    audio.onended = () => {
      URL.revokeObjectURL(audioUrl);
      isPlayingAudioRef.current = false;
      playNextAudio();
      if (audioQueueRef.current.length === 0 && !isStreaming) {
        setVoiceState(null);
      }
    };
    audio.onerror = () => {
      URL.revokeObjectURL(audioUrl);
      isPlayingAudioRef.current = false;
      playNextAudio();
    };
    audio.play().catch(err => {
      console.error("Audio play failed:", err);
      isPlayingAudioRef.current = false;
      playNextAudio();
    });
  };

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
        if (ttsBufferRef.current.trim()) {
           fetchAndQueueTTS(ttsBufferRef.current.trim());
           ttsBufferRef.current = "";
        }
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
        const token = data.token;
        ttsBufferRef.current += token;
        
        let text = ttsBufferRef.current;
        const match = text.match(/([.?!]+|\n)(?=\s|$)/);
        if (match) {
           const splitIndex = match.index + match[0].length;
           const chunk = text.slice(0, splitIndex).trim();
           if (chunk) fetchAndQueueTTS(chunk);
           ttsBufferRef.current = text.slice(splitIndex);
        } else if (text.length > 50 && text.includes(' ')) {
           const lastSpace = text.lastIndexOf(' ');
           const chunk = text.slice(0, lastSpace).trim();
           if (chunk) fetchAndQueueTTS(chunk);
           ttsBufferRef.current = text.slice(lastSpace);
        }
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

  // Auto-resize textarea as text grows
  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.style.height = "auto";
      inputRef.current.style.height = Math.min(inputRef.current.scrollHeight, 120) + "px";
    }
  }, [input]);

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
  // Messaging Logic
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
  const startRecording = async () => {
    let initialText = input.trim();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
          ? "audio/webm;codecs=opus"
          : "audio/webm",
      });

      audioChunksRef.current = [];
      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) audioChunksRef.current.push(event.data);
      };

      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        clearInterval(recognitionIntervalRef.current);
        const audioBlob = new Blob(audioChunksRef.current, { type: "audio/webm" });
        await processVoiceInput(audioBlob, true, initialText);
      };

      mediaRecorderRef.current = mediaRecorder;
      mediaRecorder.start(1000);
      setIsRecording(true);
      setRecordingMode("batch");
      setVoiceState("recording");

      // Interval for fast intermediate feedback (ChatGPT style)
      recognitionIntervalRef.current = setInterval(async () => {
        if (audioChunksRef.current.length > 0) {
          const audioBlob = new Blob(audioChunksRef.current, { type: "audio/webm" });
          await processVoiceInput(audioBlob, false, initialText);
        }
      }, 700);

      // --- SILENCE DETECTION (VAD) ---
      const audioContext = new (window.AudioContext || window.webkitAudioContext)();
      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      audioContextRef.current = audioContext;
      const bufferLength = analyser.frequencyBinCount;
      const dataArray = new Uint8Array(bufferLength);
      
      let lastSpeakTime = Date.now();
      const checkSilence = () => {
        if (!mediaRecorderRef.current || mediaRecorderRef.current.state !== "recording") return;
        analyser.getByteTimeDomainData(dataArray);
        
        // Calculate root mean square (RMS) for more accurate volume
        let sum = 0;
        for (let i = 0; i < bufferLength; i++) {
          const amplitude = dataArray[i] - 128;
          sum += amplitude * amplitude;
        }
        const rms = Math.sqrt(sum / bufferLength);

        if (rms > 5) { // Time domain threshold (5 out of 128)
          lastSpeakTime = Date.now();
        } else {
          // If silent for 1.5 seconds, stop recording
          if (Date.now() - lastSpeakTime > 1500) {
            stopRecording();
            return;
          }
        }
        requestAnimationFrame(checkSilence);
      };
      
      requestAnimationFrame(checkSilence);

    } catch (err) {
      console.error("Mic access denied:", err);
      alert("Microphone access is required.");
    }
  };

  const stopRecording = () => {
    if (recordingMode === "batch" && mediaRecorderRef.current && mediaRecorderRef.current.state === "recording") {
      mediaRecorderRef.current.stop();
    } else if (recordingMode === "stream") {
      if (asrWsRef.current) {
        if (asrWsRef.current.readyState === WebSocket.OPEN) {
          asrWsRef.current.send(new ArrayBuffer(0)); // signal end to server
          asrWsRef.current.close();
        }
        asrWsRef.current = null;
      }
      if (mediaRecorderRef.current) {
        const { stream, processor, source } = mediaRecorderRef.current;
        if (processor) processor.disconnect();
        if (source) source.disconnect();
        if (stream) stream.getTracks().forEach(t => t.stop());
        mediaRecorderRef.current = null;
      }
    }
    setIsRecording(false);
    setRecordingMode(null);
    if (audioContextRef.current && recordingMode === "stream") {
       audioContextRef.current.close().catch(() => {});
       audioContextRef.current = null;
    }
  };

  const startStreamingRecording = async () => {
    let currentCommitted = input.trim();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      
      const ws = new WebSocket(`${WS_URL}/ws/asr-stream`);
      asrWsRef.current = ws;

      ws.onopen = () => {
        setIsRecording(true);
        setRecordingMode("stream");
        setVoiceState("recording");

        const audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
        audioContextRef.current = audioContext;
        const source = audioContext.createMediaStreamSource(stream);
        
        // Setup analyser for silence detection (frontend VAD)
        const analyser = audioContext.createAnalyser();
        analyser.fftSize = 256;
        source.connect(analyser);
        const bufferLength = analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);
        
        let lastSpeakTime = Date.now();
        const checkSilence = () => {
          if (!asrWsRef.current || asrWsRef.current.readyState !== WebSocket.OPEN) return;
          analyser.getByteTimeDomainData(dataArray);
          
          let sum = 0;
          for (let i = 0; i < bufferLength; i++) {
            const amplitude = dataArray[i] - 128;
            sum += amplitude * amplitude;
          }
          const rms = Math.sqrt(sum / bufferLength);

          if (rms > 5) { // Time domain threshold (5 out of 128)
            lastSpeakTime = Date.now();
          } else {
            // Stop streaming if silent for 1.5 seconds
            if (Date.now() - lastSpeakTime > 1500) {
              stopRecording();
              return;
            }
          }
          requestAnimationFrame(checkSilence);
        };
        requestAnimationFrame(checkSilence);

        // Setup processor for PCM extraction
        const processor = audioContext.createScriptProcessor(4096, 1, 1);
        
        source.connect(processor);
        processor.connect(audioContext.destination);

        processor.onaudioprocess = (e) => {
          const inputData = e.inputBuffer.getChannelData(0);
          const pcmData = new Int16Array(inputData.length);
          for (let i = 0; i < inputData.length; i++) {
            let s = Math.max(-1, Math.min(1, inputData[i]));
            pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
          }
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(pcmData.buffer);
          }
        };

        mediaRecorderRef.current = { stream, processor, source, analyser };
      };

      ws.onmessage = (event) => {
        const res = JSON.parse(event.data);
        if (res.partial) {
          const partialText = res.partial.trim();
          if (partialText) {
            setInput(currentCommitted + (currentCommitted ? " " : "") + partialText);
          }
        } else if (res.text) {
          const finalChunk = res.text.trim();
          if (finalChunk) {
            currentCommitted = currentCommitted + (currentCommitted ? " " : "") + finalChunk;
            setInput(currentCommitted);
          }
        } else if (res.done) {
          stopRecording();
        }
      };

      ws.onclose = () => stopRecording();

    } catch (err) {
      console.error("Mic access denied:", err);
      alert("Microphone access is required.");
    }
  };

  const toggleRecording = () => {
    if (isRecording) stopRecording();
    else startRecording();
  };

  const processVoiceInput = async (audioBlob, isFinal = false, initialText = "") => {
    if (!isFinal) setVoiceState("recording");
    else setVoiceState("processing");

    try {
      const formData = new FormData();
      formData.append("file", audioBlob, "recording.webm");
      const resp = await fetch(`${API_URL}/api/voice/transcribe`, { method: "POST", body: formData });
      if (resp.ok) {
        const result = await resp.json();
        const text = result.text?.trim();
        if (text) {
          setInput(initialText + (initialText ? " " : "") + text);
        }
      }
    } catch (err) {
      console.warn("ASR Error:", err);
    } finally {
      if (isFinal) {
        setVoiceState(null);
        if (audioContextRef.current) {
          audioContextRef.current.close().catch(() => {});
          audioContextRef.current = null;
        }
      }
    }
  };

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
                        {msg.streaming && msg.content === "" && msg.role === "assistant" && (
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
          {voiceState && voiceState !== "recording" && (
            <div className={`voice-status ${voiceState}`}>
              {voiceState === "processing" && "⏳ Processing your voice..."}
              {voiceState === "speaking" && "🔊 Playing response..."}
            </div>
          )}

          <div className="input-wrapper">
            {/* Microphone button (Batch) */}
            <button
              className={`mic-btn ${isRecording && recordingMode === "batch" ? "recording" : ""}`}
              onClick={toggleRecording}
              disabled={(isRecording && recordingMode !== "batch") || !isConnected || isStreaming || voiceState === "processing"}
              title={isRecording && recordingMode === "batch" ? "Stop recording" : "Start Whisper (Batch)"}
            >
              {isRecording && recordingMode === "batch" ? "⏹" : "🎤"}
            </button>

            {/* Microphone button (Stream) */}
            <button
              className={`mic-btn ${isRecording && recordingMode === "stream" ? "recording" : ""}`}
              onClick={() => isRecording ? stopRecording() : startStreamingRecording()}
              disabled={(isRecording && recordingMode !== "stream") || !isConnected || isStreaming || voiceState === "processing"}
              title={isRecording && recordingMode === "stream" ? "Stop stream" : "Start Vosk (Stream)"}
              style={{ marginLeft: "8px" }}
            >
              {isRecording && recordingMode === "stream" ? "⏹" : "🎙️"}
            </button>

            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Message Sara..."
              rows={1}
              disabled={!isConnected || isStreaming || !activeChat || isRecording}
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