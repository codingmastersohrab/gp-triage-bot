import { useState, useRef, useEffect } from 'react'
import './App.css'

const API_BASE = 'http://127.0.0.1:8000'

const OPENING_MESSAGE =
  "What's the main issue you're calling about today? (One sentence is fine.)"

const SpeechRecognition =
  window.SpeechRecognition || window.webkitSpeechRecognition || null

const ROUTE_CONFIG = {
  EMERGENCY_NOW:    { label: 'Emergency — Call 999 / Go to A&E',    colour: 'emergency', icon: '🚨' },
  URGENT_SAME_DAY:  { label: 'Urgent — Same-day GP / Urgent Care',  colour: 'urgent',    icon: '⚠️' },
  ROUTINE_GP:       { label: 'Routine GP Appointment',              colour: 'routine',   icon: '📋' },
}

export default function App() {
  const [phase, setPhase]         = useState('idle')
  const [sessionId, setSessionId] = useState(null)
  const [session, setSession]     = useState(null)
  const [messages, setMessages]   = useState([])
  const [inputText, setInputText] = useState('')
  const [loading, setLoading]     = useState(false)
  const [recording, setRecording] = useState(false)
  const [error, setError]         = useState(null)

  const bottomRef      = useRef(null)
  const recognitionRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const isComplete = session?.summary_confirmed === true
  const routeKey   = session?.route_outcome

  async function startSession() {
    setLoading(true); setError(null)
    try {
      const res = await fetch(`${API_BASE}/session/start`, { method: 'POST' })
      if (!res.ok) throw new Error(`Server error: ${res.status}`)
      const data = await res.json()
      setSessionId(data.session.session_id)
      setSession(data.session)
      setMessages([{ role: 'bot', text: OPENING_MESSAGE }])
      setPhase('chatting')
    } catch (err) {
      setError(`Could not reach the server: ${err.message}`)
    } finally { setLoading(false) }
  }

  async function sendMessage() {
    const text = inputText.trim()
    if (!text || loading) return
    setMessages(prev => [...prev, { role: 'user', text }])
    setInputText('')
    setLoading(true); setError(null)
    try {
      const res = await fetch(`${API_BASE}/session/${sessionId}/user_input`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      })
      if (!res.ok) throw new Error(`Server error: ${res.status}`)
      const data = await res.json()
      setSession(data.session)
      setMessages(prev => [...prev, { role: 'bot', text: data.bot_message }])
    } catch (err) {
      setError(`Failed to send message: ${err.message}`)
    } finally { setLoading(false) }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() }
  }

  function startRecording() {
    if (!sessionId)          { setError('Start a session before recording.'); return }
    if (!SpeechRecognition)  { setError('Speech recognition not supported. Use Chrome or Edge.'); return }
    setError(null)
    const recognition = new SpeechRecognition()
    recognition.lang = 'en-GB'; recognition.continuous = false; recognition.interimResults = false
    recognitionRef.current = recognition
    let gotResult = false
    recognition.onstart  = () => setRecording(true)
    recognition.onresult = async (event) => {
      gotResult = true
      const transcript = event.results[0][0].transcript.trim()
      setRecording(false)
      if (!transcript) { setError('No speech detected. Please try again.'); return }
      await sendVoiceTranscript(transcript)
    }
    recognition.onerror = (event) => {
      gotResult = true; setRecording(false)
      if (event.error === 'not-allowed')  setError('Microphone access denied.')
      else if (event.error === 'no-speech') setError('No speech detected. Please try again.')
      else setError(`Speech recognition error: ${event.error}`)
    }
    recognition.onend = () => {
      setRecording(false)
      if (!gotResult) setError('Microphone not ready — tap the mic button again and speak immediately.')
    }
    recognition.start()
  }

  function stopRecording() { recognitionRef.current?.stop() }

  function resetToHome() {
    recognitionRef.current?.stop()
    setPhase('idle')
    setSessionId(null)
    setSession(null)
    setMessages([])
    setInputText('')
    setLoading(false)
    setRecording(false)
    setError(null)
  }

  async function sendVoiceTranscript(transcript) {
    setMessages(prev => [...prev, { role: 'user', text: `(voice) ${transcript}`, voice: true }])
    setLoading(true); setError(null)
    try {
      const res = await fetch(`${API_BASE}/session/${sessionId}/user_input`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: transcript }),
      })
      if (!res.ok) throw new Error(`Server error: ${res.status}`)
      const data = await res.json()
      setSession(data.session)
      setMessages(prev => [...prev, { role: 'bot', text: data.bot_message }])
    } catch (err) {
      setError(`Failed to send voice message: ${err.message}`)
    } finally { setLoading(false) }
  }

  return (
    <div className="container">
      <div className="header">
        <span className="header-icon">🏥</span>
        <div>
          <h1>GP Triage Assistant</h1>
          <p>Primary Care — Intake &amp; Routing Tool</p>
        </div>
      </div>

      <div className="body">
        {phase === 'idle' ? (
          <>
            <div className="idle-hero">
              <span className="idle-hero-icon">🩺</span>
              <h2>Welcome to the GP Triage Assistant</h2>
              <p>Answer a few short questions to help your practice prepare for your visit.</p>
            </div>
            <div className="idle-cards">
              <div className="idle-card"><span>💬</span>Guided conversation</div>
              <div className="idle-card"><span>🎤</span>Voice or text</div>
              <div className="idle-card"><span>📋</span>Handed to your GP</div>
            </div>
            <div className="idle-warning">
              ⚠️ This tool does <strong>not</strong> diagnose or prescribe. If you are
              in an emergency, call <strong>999</strong> immediately.
            </div>
            {error && <div className="error">{error}</div>}
            <button className="start-btn" onClick={startSession} disabled={loading}>
              {loading ? 'Starting…' : 'Begin Triage'}
            </button>
          </>
        ) : (
          <>
            <p className="session-id">Session ID: {sessionId}</p>

            <div className="chat-window">
              {messages.map((msg, i) => (
                <div key={i} className={`message ${msg.role}`}>
                  <span className="message-label">
                    {msg.role === 'bot' ? 'Assistant' : msg.voice ? '🎤 You (voice)' : 'You'}
                  </span>
                  <span className="bubble">{msg.text}</span>
                </div>
              ))}
              {(loading || recording) && (
                <div className="message bot">
                  <span className="bubble typing">{recording ? 'Listening…' : 'Thinking…'}</span>
                </div>
              )}
              <div ref={bottomRef} />
            </div>

            {isComplete && routeKey && ROUTE_CONFIG[routeKey] && (
              <div className={`summary-card summary-card--${ROUTE_CONFIG[routeKey].colour}`}>
                <div className="summary-card__header">
                  <span className="summary-card__icon">{ROUTE_CONFIG[routeKey].icon}</span>
                  <span className="summary-card__route">{ROUTE_CONFIG[routeKey].label}</span>
                </div>
                <div className="summary-card__body">
                  {session.main_issue && <p><strong>Concern:</strong> {session.main_issue}</p>}
                  {session.duration   && <p><strong>Duration:</strong> {session.duration.value} {session.duration.unit}</p>}
                  {session.severity_0_10 != null && <p><strong>Severity:</strong> {session.severity_0_10}/10</p>}
                  {session.symptom_category && <p><strong>Category:</strong> {session.symptom_category.replace(/_/g, ' ')}</p>}
                  {session.route_rationale  && <p className="summary-card__rationale">{session.route_rationale}</p>}
                </div>
                <p className="summary-card__disclaimer">
                  This is not a medical diagnosis. If symptoms worsen, call NHS 111 or 999 in an emergency.
                </p>
                <button className="home-btn" onClick={resetToHome}>← Back to Home</button>
              </div>
            )}

            {error && <div className="error">{error}</div>}

            {!isComplete && (
              <div className="input-row">
                <input
                  type="text"
                  value={inputText}
                  onChange={e => setInputText(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Type your response and press Enter…"
                  disabled={loading || recording}
                  autoFocus
                />
                <button className="send-btn" onClick={sendMessage}
                  disabled={loading || recording || !inputText.trim()}>Send</button>
                {recording ? (
                  <button className="mic-btn mic-btn--stop" onClick={stopRecording} title="Stop recording">
                    <span className="mic-dot" />Stop
                  </button>
                ) : (
                  <button className="mic-btn" onClick={startRecording} disabled={loading} title="Record voice message">
                    🎤
                  </button>
                )}
              </div>
            )}

            <p className="safety-notice">
              This system does not diagnose. If symptoms worsen, contact NHS 111 or call 999 in an emergency.
            </p>
          </>
        )}
      </div>
    </div>
  )
}
