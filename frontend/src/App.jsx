import { useEffect, useRef, useState } from 'react';

const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '');

function createSessionId() {
  return `s-${crypto.randomUUID()}`;
}

function newConversation() {
  return { id: createSessionId(), title: 'New conversation', messages: [] };
}

function ErrorText({ status }) {
  if (status === 422) return 'That message could not be sent. Check the session and message length, then try again.';
  if (status === 503) return 'Lyftr AI is temporarily unavailable because all configured providers failed. Please try again shortly.';
  return 'We could not reach Lyftr AI. Check your connection and try again.';
}

function Metadata({ metadata }) {
  return <div className="metadata" aria-label="Response metadata">
    <span data-testid="meta-source">{metadata.resolution_source}</span>
    <span data-testid="meta-model">{metadata.model}</span>
    <span><b data-testid="meta-latency">{metadata.latency_ms} ms</b></span>
    <span>In <b data-testid="meta-input-tokens">{metadata.input_tokens}</b></span>
    <span>Out <b data-testid="meta-output-tokens">{metadata.output_tokens}</b></span>
  </div>;
}

export default function App() {
  const [conversations, setConversations] = useState(() => [newConversation()]);
  const [activeId, setActiveId] = useState(() => null);
  const [input, setInput] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [showPrompt, setShowPrompt] = useState(false);
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef(null);
  const active = conversations.find((conversation) => conversation.id === activeId) || conversations[0];

  useEffect(() => { if (!activeId) setActiveId(conversations[0].id); }, [activeId, conversations]);
  useEffect(() => { scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' }); }, [active?.messages, loading]);

  // Restore server history when an existing session is selected from the sidebar.
  async function selectConversation(conversation) {
    setActiveId(conversation.id);
    if (conversation.messages.length) return;
    try {
      const response = await fetch(`${API_URL}/sessions/${encodeURIComponent(conversation.id)}/messages`);
      if (!response.ok) return; // A fresh client session is expected to return 404.
      const data = await response.json();
      setConversations((items) => items.map((item) => item.id === conversation.id ? { ...item, messages: data.messages } : item));
    } catch { /* A history fetch should not blank or block the chat UI. */ }
  }

  function updateActiveMessages(messages) {
    setConversations((items) => items.map((item) => item.id === active.id ? { ...item, messages } : item));
  }

  async function sendMessage(event) {
    event?.preventDefault();
    const message = input.trim();
    if (!message || loading) return;

    // Add the user's text immediately; only the latest message is sent to the API.
    const userMessage = { role: 'user', content: message };
    updateActiveMessages([...active.messages, userMessage]);
    setInput('');
    setLoading(true);
    setConversations((items) => items.map((item) => item.id === active.id && item.title === 'New conversation'
      ? { ...item, title: message.slice(0, 34) } : item));

    try {
      const response = await fetch(`${API_URL}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: active.id, message, ...(systemPrompt.trim() ? { system_prompt: systemPrompt.trim() } : {}) }),
      });
      if (!response.ok) {
        const error = new Error('request failed');
        error.status = response.status;
        throw error;
      }
      const data = await response.json();
      updateActiveMessages([...active.messages, userMessage, { role: 'assistant', content: data.reply, metadata: data.metadata }]);
    } catch (error) {
      updateActiveMessages([...active.messages, userMessage, { role: 'error', content: <ErrorText status={error.status} /> }]);
    } finally {
      setLoading(false);
    }
  }

  function startConversation() {
    const conversation = newConversation();
    setConversations((items) => [conversation, ...items]);
    setActiveId(conversation.id);
    setSystemPrompt('');
    setInput('');
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark">L</div><div><strong>lyftr<span>ai</span></strong><small>YOUR THOUGHT PARTNER</small></div></div>
      <button className="new-chat" onClick={startConversation}><span>＋</span> New chat <kbd>⌘ K</kbd></button>
      <div className="history-label">RECENT</div>
      <nav className="history-list" aria-label="Chat history">
        {conversations.map((conversation) => <button key={conversation.id} className={`history-item ${active.id === conversation.id ? 'selected' : ''}`} onClick={() => selectConversation(conversation)}>
          <span className="history-icon">◌</span><span>{conversation.title}</span>
        </button>)}
      </nav>
      <div className="sidebar-bottom"><span className="status-dot" /> System operational <span className="version">v1.0</span></div>
    </aside>

    <main className="main-panel">
      <header className="topbar"><div className="mobile-brand">LYFTR <span>AI</span></div><div className="model-chip"><i /> Lyftr assistant <span>LiteLLM</span></div><button className="avatar" aria-label="Profile">A</button></header>
      <section className={`conversation ${active.messages.length ? 'has-messages' : ''}`} ref={scrollRef}>
        {active.messages.length === 0 ? <div className="welcome">
          <div className="welcome-orb"><span>✳</span></div>
          <p className="eyebrow">A LITTLE MORE CLARITY, EVERY DAY</p>
          <h1>Good ideas start<br />with a <em>conversation.</em></h1>
          <p className="welcome-copy">Ask anything. Explore an idea. Figure out what comes next.</p>
          <div className="suggestions">
            {['Help me think through a new idea', 'Explain something simply', 'Draft a thoughtful email'].map((suggestion) => <button key={suggestion} onClick={() => setInput(suggestion)}>{suggestion}<span>↗</span></button>)}
          </div>
        </div> : <div className="messages">
          {active.messages.map((message, index) => <article key={`${active.id}-${index}`} className={`message-row ${message.role}`} data-testid={message.role === 'assistant' ? 'assistant-message' : undefined}>
            {message.role === 'assistant' && <div className="assistant-icon">✳</div>}
            <div className="message-content">
              <div className="bubble">{message.content}</div>
              {message.metadata && <Metadata metadata={message.metadata} />}
            </div>
            {message.role === 'user' && <div className="user-icon">A</div>}
          </article>)}
          {loading && <div className="message-row assistant"><div className="assistant-icon">✳</div><div className="thinking"><span /><span /><span /> <small>Thinking</small></div></div>}
        </div>}
      </section>
      <footer className="composer-wrap">
        {showPrompt && <label className="prompt-field"><span>SESSION SYSTEM PROMPT</span><textarea data-testid="system-prompt-input" value={systemPrompt} onChange={(event) => setSystemPrompt(event.target.value)} placeholder="Guide how Lyftr AI responds in this chat…" rows="2" /></label>}
        <form className="composer" onSubmit={sendMessage}>
          <textarea data-testid="chat-input" value={input} onChange={(event) => setInput(event.target.value)} placeholder="Message Lyftr AI…" rows="1" onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); sendMessage(); } }} />
          <div className="composer-tools"><button type="button" className={`prompt-toggle ${showPrompt ? 'active' : ''}`} onClick={() => setShowPrompt(!showPrompt)} title="Set a system prompt">⌘ <span>System prompt</span></button><span className="composer-hint">ENTER TO SEND</span><button data-testid="send-button" type="submit" className="send-button" disabled={loading || !input.trim()} aria-label="Send message">↑</button></div>
        </form>
        <p className="disclaimer">Lyftr AI can make mistakes. Check important information.</p>
      </footer>
    </main>
  </div>;
}
