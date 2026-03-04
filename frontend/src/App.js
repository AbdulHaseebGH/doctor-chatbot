import { useState, useEffect, useRef, useCallback } from "react";
import "./App.css";
import ReactMarkdown from 'react-markdown';

const GATEWAY_URL = "http://localhost:8000";
const WS_URL = "ws://localhost:8000";

let chatCounter = 1;

function App() {
  const [chats, setChats] = useState([]); // [{id, sessionId, title, messages}]
  const [activeChatId, setActiveChatId] = useState(null);
  const [input, setInput] = useState("");
  const [isConnected, setIsConnected] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const wsRef = useRef(null);
  const bottomRef = useRef(null);
  const inputRef = useRef(null);

  const createSession = async () => {
    const res = await fetch(`${GATEWAY_URL}/session`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const data = await res.json();
    return data.session_id;
  };

  const connectWebSocket = useCallback((sessionId, chatId) => {
    if (wsRef.current) wsRef.current.close();
    const ws = new WebSocket(`${WS_URL}/ws/chat/${sessionId}`);
    ws.onopen = () => setIsConnected(true);
    ws.onclose = () => setIsConnected(false);
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.done) {
        setIsStreaming(false);
        // Mark streaming done
        setChats((prev) =>
          prev.map((c) => {
            if (c.id !== chatId) return c;
            const msgs = [...c.messages];
            const last = msgs[msgs.length - 1];
            if (last?.role === "assistant") {
              msgs[msgs.length - 1] = { ...last, streaming: false };
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

const createNewChat = useCallback(async () => {
  const res = await fetch(`${GATEWAY_URL}/session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  const data = await res.json();
  const chatId = `chat-${Date.now()}`;
  const welcomeMsg = {
    role: "assistant",
    content: "Hello! I'm Sara, the receptionist at City Medical Clinic. May I have your name please?",
    streaming: false,
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
  connectWebSocket(data.session_id, chatId);
}, [connectWebSocket]);

  // Init with one chat
  useEffect(() => {
    createNewChat();
    return () => wsRef.current?.close();
  }, []);

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chats, activeChatId]);

  const switchChat = (chat) => {
    if (isStreaming) return;
    setActiveChatId(chat.id);
    setInput("");
    connectWebSocket(chat.sessionId, chat.id);
  };

  const deleteChat = async (e, chat) => {
    e.stopPropagation();
    await fetch(`${GATEWAY_URL}/session/${chat.sessionId}`, { method: "DELETE" });
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

  const sendMessage = () => {
    if (!input.trim() || !isConnected || isStreaming) return;
    const userMsg = { role: "user", content: input.trim(), streaming: false };
    const assistantMsg = { role: "assistant", content: "", streaming: true };

    // Auto-title chat from first user message
    setChats((prev) =>
      prev.map((c) => {
        if (c.id !== activeChatId) return c;
        const isFirst = c.messages.filter((m) => m.role === "user").length === 0;
        return {
          ...c,
          title: isFirst ? input.trim().slice(0, 30) + (input.length > 30 ? "..." : "") : c.title,
          messages: [...c.messages, userMsg, assistantMsg],
        };
      })
    );

    setIsStreaming(true);
    wsRef.current.send(JSON.stringify({ message: input.trim() }));
    setInput("");
    inputRef.current?.focus();
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const activeChat = chats.find((c) => c.id === activeChatId);

  return (
    <div className="app">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-top">
          <div className="clinic-brand">
            <span className="brand-icon">⚕</span>
            <span className="brand-name">City Clinic</span>
          </div>
          <button className="new-chat-btn" onClick={createNewChat}>
            <span>+</span> New Chat
          </button>
        </div>

        <div className="chat-list">
          {chats.length === 0 && (
            <p className="no-chats">No chats yet</p>
          )}
          {chats.map((chat) => (
            <div
              key={chat.id}
              className={`chat-item ${chat.id === activeChatId ? "active" : ""}`}
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

      {/* Main Chat */}
      <main className="chat-main">
        <div className="chat-header">
          <h1>
            {activeChat?.title || "Sara"}
            <span className="subtitle"> — Medical Receptionist</span>
          </h1>
        </div>

        <div className="messages-container">
          {activeChat?.messages.map((msg, i) => (
            <div key={i} className={`message-row ${msg.role}`}>
              {msg.role === "assistant" && (
                <div className="avatar assistant-avatar">S</div>
              )}
              <div className={`bubble ${msg.role}`}>
                {msg.role === 'assistant' ? (
                  <ReactMarkdown>{msg.content}</ReactMarkdown>
                ) : (
                  msg.content
                )}
                {msg.streaming && msg.content === "" && (
                  <span className="typing-dots">
                    <span>.</span><span>.</span><span>.</span>
                  </span>
                )}
              </div>
              {msg.role === "user" && (
                <div className="avatar user-avatar">U</div>
              )}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        <div className="input-area">
          <div className="input-wrapper">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Message Sara..."
              rows={1}
              disabled={!isConnected || isStreaming || !activeChat}
            />
            <button
              className="send-btn"
              onClick={sendMessage}
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