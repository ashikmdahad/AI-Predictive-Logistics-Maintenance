import React, { useEffect, useMemo, useRef, useState } from 'react'
import { ResponsiveContainer, LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip, AreaChart, Area } from 'recharts'
import { format, parseISO } from 'date-fns'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function useWebSocketFeed(){
  const [messages, setMessages] = useState([])
  const wsRef = useRef(null)

  useEffect(()=>{
    const ws = new WebSocket(API.replace('http','ws') + '/readings/ws')
    wsRef.current = ws
    ws.onmessage = e => setMessages(m => [JSON.parse(e.data), ...m].slice(0, 100))
    ws.onopen = () => ws.send('ping')
    const id = setInterval(()=> ws.readyState === 1 && ws.send('ping'), 10000)
    return ()=>{ clearInterval(id); ws.close() }
  },[])

  return messages
}

function Card({ title, action, children }){
  return (
    <div className="card">
      <div className="section-title">
        <h3>{title}</h3>
        {action}
      </div>
      {children}
    </div>
  )
}

function MetricCard({ label, value, sub }){
  return (
    <div className="metric-card">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      {sub && <div className="metric-sub">{sub}</div>}
    </div>
  )
}

function formatTime(ts){
  try{
    return format(parseISO(ts), 'MMM d HH:mm')
  }catch(err){
    return ts
  }
}

function StatBadge({ label }){
  return <span className="pill pill-plain">{label}</span>
}

function WhatIf({ deviceId, baseline, onPreview, loading, result }){
  const defaults = { vibration: 2.2, temperature: 60, current: 10, rpm: 1500, load_pct: 65 }
  const [form, setForm] = useState(defaults)

  useEffect(()=>{
    if(baseline){
      setForm({
        vibration: Number(baseline.vibration ?? defaults.vibration),
        temperature: Number(baseline.temperature ?? defaults.temperature),
        current: Number(baseline.current ?? defaults.current),
        rpm: Number(baseline.rpm ?? defaults.rpm),
        load_pct: Number(baseline.load_pct ?? defaults.load_pct),
      })
    }else{
      setForm(defaults)
    }
  },[baseline, deviceId])

  async function submit(){
    if(!deviceId) return
    const payload = {
      device_id: deviceId,
      vibration: Number(form.vibration),
      temperature: Number(form.temperature),
      current: Number(form.current),
      rpm: Number(form.rpm),
      load_pct: Number(form.load_pct),
      timestamp: new Date().toISOString(),
    }
    await onPreview(payload)
  }

  return (
    <div>
      <div className="small" style={{marginBottom:6}}>Test scenarios before dispatching technicians.</div>
      {['vibration','temperature','current','rpm','load_pct'].map(key => (
        <div key={key} style={{margin:'6px 0'}}>
          <label className="small" style={{textTransform:'capitalize'}}>{key.replace('_',' ')}</label>
          <input
            className="input"
            type="number"
            step="any"
            value={form[key]}
            onChange={e => setForm(prev => ({...prev, [key]: e.target.value}))}
          />
        </div>
      ))}
      <button className="btn" onClick={submit} disabled={loading || !deviceId}>{loading ? 'Scoring...' : 'Preview Risk'}</button>
      {typeof result === 'number' && (
        <p style={{marginTop:12}}>Predicted failure risk: <b>{(result * 100).toFixed(1)}%</b></p>
      )}
      {!deviceId && <p className="small" style={{marginTop:10}}>Select an asset to run a what-if scenario.</p>}
    </div>
  )
}

function Dashboard(){
  const [devices, setDevices] = useState([])
  const [alerts, setAlerts] = useState([])
  const [preds, setPreds] = useState([])
  const [metrics, setMetrics] = useState({})
  const [config, setConfig] = useState({ provider: 'local' })
  const [history, setHistory] = useState([])
  const [selectedDevice, setSelectedDevice] = useState(null)
  const [whatIfResult, setWhatIfResult] = useState(null)
  const [whatIfLoading, setWhatIfLoading] = useState(false)
  const [loading, setLoading] = useState(false)
  const feed = useWebSocketFeed()
  const [assistantMode, setAssistantMode] = useState('')
  const [assistantNotes, setAssistantNotes] = useState('')
  const [assistantResponse, setAssistantResponse] = useState(null)
  const [assistantLoading, setAssistantLoading] = useState(false)
  const [assistantError, setAssistantError] = useState(null)
  const [userRole, setUserRole] = useState('manager')
  const [assistantLogs, setAssistantLogs] = useState([])
  const [assistantLogsLoading, setAssistantLogsLoading] = useState(false)
  const [feedbackOutcome, setFeedbackOutcome] = useState('resolved')
  const [feedbackNotes, setFeedbackNotes] = useState('')
  const [feedbackSubmittedBy, setFeedbackSubmittedBy] = useState('')
  const [feedbackProbability, setFeedbackProbability] = useState('')
  const [feedbackSaving, setFeedbackSaving] = useState(false)
  const [feedbackMessage, setFeedbackMessage] = useState(null)
  const roleOptions = [
    { id: 'manager', label: 'Manager' },
    { id: 'technician', label: 'Technician' },
    { id: 'dispatcher', label: 'Dispatcher' },
  ]
  const assistantModes = config.assistant_modes || []

  async function loadCore(){
    setLoading(true)
    setAssistantLogsLoading(true)
    try{
      const [dRes, aRes, pRes, mRes, cRes, logsRes] = await Promise.all([
        fetch(`${API}/devices/`),
        fetch(`${API}/insights/alerts`),
        fetch(`${API}/insights/predictions`),
        fetch(`${API}/insights/metrics`),
        fetch(`${API}/insights/config`),
        fetch(`${API}/insights/assistant/logs?limit=40`),
      ])

      const [d, a, p, m, c, logsJson] = await Promise.all([
        dRes.ok ? dRes.json() : Promise.resolve([]),
        aRes.ok ? aRes.json() : Promise.resolve([]),
        pRes.ok ? pRes.json() : Promise.resolve([]),
        mRes.ok ? mRes.json() : Promise.resolve({}),
        cRes.ok ? cRes.json() : Promise.resolve({ provider: 'local' }),
        logsRes.ok ? logsRes.json() : Promise.resolve([]),
      ])

      setDevices(Array.isArray(d) ? d : [])
      setAlerts(Array.isArray(a) ? a : [])
      setPreds(Array.isArray(p) ? p : [])
      setMetrics(m || {})
      setConfig(c || { provider: 'local' })
      setAssistantLogs(Array.isArray(logsJson) ? logsJson : [])

      if(!selectedDevice && Array.isArray(d) && d.length){
        setSelectedDevice(d[0].id)
      }
    }catch(err){
      console.error('Failed to load logistics dashboard data', err)
      setAssistantLogs([])
    }finally{
      setLoading(false)
      setAssistantLogsLoading(false)
    }
  }

  async function loadHistory(deviceId){
    if(!deviceId){
      setHistory([])
      return
    }
    try{
      const res = await fetch(`${API}/devices/${deviceId}/readings?limit=60`)
      if(!res.ok){
        setHistory([])
        return
      }
      const data = await res.json()
      setHistory(Array.isArray(data) ? data : [])
    }catch(err){
      console.error('Failed to load telemetry history', err)
      setHistory([])
    }
  }

  useEffect(()=>{ loadCore() },[])

  useEffect(()=>{
    if(!assistantMode && assistantModes.length){
      setAssistantMode(assistantModes[0].id)
    }
  }, [assistantMode, assistantModes])

  useEffect(()=>{
    setAssistantResponse(null)
    setAssistantError(null)
  }, [assistantMode])

  useEffect(()=>{
    if(selectedDevice){
      loadHistory(selectedDevice)
      setWhatIfResult(null)
    }
  },[selectedDevice])

  const historySeries = useMemo(()=> history.map(r => ({
    timestamp: r.timestamp,
    temperature: Number(r.temperature ?? 0),
    vibration: Number(r.vibration ?? 0),
    load_pct: Number(r.load_pct ?? 0),
  })), [history])

  const riskSeries = useMemo(()=> preds
    .filter(p => p.device_id === selectedDevice)
    .slice()
    .reverse()
    .map(p => ({ timestamp: p.timestamp, probability: p.probability })), [preds, selectedDevice])

  const selectedAssistantMode = useMemo(
    () => assistantModes.find(mode => mode.id === assistantMode) || null,
    [assistantModes, assistantMode]
  )

  const thresholdPercent = useMemo(
    () => Math.round((config?.alert_prob_threshold ?? 0.6) * 100),
    [config]
  )

  const deviceSnapshots = metrics.device_snapshots || []
  const snapshotMap = useMemo(()=>{
    const map = {}
    deviceSnapshots.forEach(s => { map[s.id] = s })
    return map
  }, [deviceSnapshots])

  const selectedSnapshot = snapshotMap[selectedDevice] || null
  const latestReading = selectedSnapshot?.latest_reading || null
  const typeSummary = metrics.type_summary || []
  const locationSummary = metrics.location_summary || []
  const recommendations = metrics.recommendations || []
  const feedbackEntries = metrics.feedback_entries || []
  const isManager = userRole === 'manager'
  const isTechnician = userRole === 'technician'
  const isDispatcher = userRole === 'dispatcher'
  const latestProbabilityValue = selectedSnapshot && selectedSnapshot.latest_probability !== null
    ? selectedSnapshot.latest_probability
    : undefined
  const feedbackForDevice = useMemo(() => {
    if(!selectedDevice){
      return feedbackEntries
    }
    return feedbackEntries.filter(entry => entry.device_id === selectedDevice)
  }, [feedbackEntries, selectedDevice])
  const logsForDevice = useMemo(() => {
    if(!selectedDevice){
      return assistantLogs
    }
    return assistantLogs.filter(entry => entry.device_id === selectedDevice)
  }, [assistantLogs, selectedDevice])
  const renderAssistantActivityCard = () => (
    <Card title="Assistant Activity">
      <div className="feed" style={{maxHeight:300}}>
        {assistantLogsLoading && <p className="small">Loading assistant history...</p>}
        <ul className="reset">
          {logsForDevice.map(log => (
            <li key={log.id} style={{marginBottom:8}}>
              <span className="pill">{log.mode}</span>
              <div className="small">{formatTime(log.created_at)} - via {log.provider}</div>
              <div>{log.message}</div>
            </li>
          ))}
          {!assistantLogsLoading && !logsForDevice.length && <li className="small">No assistant activity captured yet.</li>}
        </ul>
      </div>
    </Card>
  )

  async function handlePreview(payload){
    setWhatIfLoading(true)
    try{
      const res = await fetch(`${API}/insights/what-if`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if(!res.ok){
        setWhatIfResult(null)
        return
      }
      const data = await res.json()
      setWhatIfResult(typeof data?.probability === 'number' ? data.probability : null)
    }catch(err){
      console.error('What-if scoring failed', err)
      setWhatIfResult(null)
    }finally{
      setWhatIfLoading(false)
    }
  }

  async function askAssistant(){
    if(!assistantMode){
      setAssistantError('Select a scenario to request assistance.')
      return
    }
    const modeMeta = assistantModes.find(mode => mode.id === assistantMode)
    if(modeMeta?.requires_device && !selectedDevice){
      setAssistantError('Select an asset above to provide context for this scenario.')
      return
    }

    setAssistantError(null)
    setAssistantLoading(true)
    try{
      const body = { mode: assistantMode, notes: assistantNotes }
      if(modeMeta?.requires_device && selectedDevice){
        body.device_id = selectedDevice
      }
      const res = await fetch(`${API}/insights/assistant`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if(!res.ok){
        throw new Error(`Assistant request failed: ${res.status}`)
      }
      const data = await res.json()
      setAssistantResponse(data)
    }catch(err){
      console.error('Assistant request failed', err)
      setAssistantResponse({ provider: 'error', message: 'Unable to contact the AI assistant. Please try again later.' })
    }finally{
      setAssistantLoading(false)
    }
  }

  async function submitFeedback(){
    setFeedbackMessage(null)
    if(!selectedDevice){
      setFeedbackMessage('Select an asset before submitting feedback.')
      return
    }
    if(!feedbackOutcome){
      setFeedbackMessage('Enter an outcome summary (e.g., component replaced, inspection scheduled).')
      return
    }
    setFeedbackSaving(true)
    try{
      const payload = {
        device_id: selectedDevice,
        outcome: feedbackOutcome,
        notes: feedbackNotes,
        submitted_by: feedbackSubmittedBy || undefined,
        related_probability: feedbackProbability ? Number(feedbackProbability) : undefined,
      }
      const res = await fetch(`${API}/insights/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if(!res.ok){
        throw new Error(`Feedback request failed: ${res.status}`)
      }
      await loadCore()
      setFeedbackNotes('')
      setFeedbackSubmittedBy('')
      setFeedbackProbability('')
      setFeedbackMessage('Maintenance feedback recorded.')
    }catch(err){
      console.error('Feedback submission failed', err)
      setFeedbackMessage('Could not record feedback, please try again later.')
    }finally{
      setFeedbackSaving(false)
    }
  }

  const deviceOptions = devices.map(d => (
    <option key={d.id} value={d.id}>{d.name}</option>
  ))

  function renderLatestReading(reading){
    if(!reading) return <p className="small">No telemetry received yet.</p>
    const temp = Number(reading.temperature ?? 0)
    const vib = Number(reading.vibration ?? 0)
    const current = Number(reading.current ?? 0)
    const rpm = Number(reading.rpm ?? 0)
    const load = Number(reading.load_pct ?? 0)
    return (
      <ul className="asset-reading">
        <li><span>Timestamp</span><b>{formatTime(reading.timestamp)}</b></li>
        <li><span>Temperature</span><b>{temp.toFixed(1)} deg C</b></li>
        <li><span>Vibration</span><b>{vib.toFixed(2)} mm/s</b></li>
        <li><span>Current</span><b>{current.toFixed(1)} A</b></li>
        <li><span>RPM</span><b>{rpm.toFixed(0)}</b></li>
        <li><span>Load</span><b>{load.toFixed(1)} %</b></li>
      </ul>
    )
  }

  return (
    <div>
      <div className="container">
        <div className="header">
          <div>
            <h1 className="title">AI Predictive Maintenance</h1>
            <div className="sub">Logistics fleet and warehouse assets monitored in real time.</div>
          </div>
          <div style={{display:'flex',alignItems:'center',gap:12}}>
            <div className="role-switch">
              <label htmlFor="role-select">View as</label>
              <select id="role-select" className="select" value={userRole} onChange={e => setUserRole(e.target.value)}>
                {roleOptions.map(role => <option key={role.id} value={role.id}>{role.label}</option>)}
              </select>
            </div>
            <span className="badge">Provider: {String(config?.provider || 'local').toUpperCase()}</span>
          </div>
        </div>

        {(isManager || isDispatcher) && (
        <div className="metrics">
          <MetricCard label="Assets" value={metrics.device_count ?? '0'} sub="Tracked trucks, conveyors, forklifts" />
          <MetricCard label="Active Alerts" value={metrics.active_alerts ?? '0'} sub="Issues needing attention" />
          <MetricCard label="Readings (24h)" value={metrics.readings_last_24h ?? '0'} sub="Telemetry ingested" />
          <MetricCard label="High Risk" value={metrics.high_risk_count ?? '0'} sub={`Risk >= ${thresholdPercent}%`} />
        </div>
        )}

        <div className="grid-3">
          <Card
            title="Assets"
            action={devices.length ? (
              <select className="select" value={selectedDevice || ''} onChange={e => setSelectedDevice(Number(e.target.value))}>
                {deviceOptions}
              </select>
            ) : null}
          >
            <table className="table">
              <thead><tr><th>Name</th><th>Type</th><th>Location</th><th>Status</th></tr></thead>
              <tbody>
                {devices.map(d => (
                  <tr key={d.id}>
                    <td>{d.name}</td>
                    <td>{d.type}</td>
                    <td>{d.location}</td>
                    <td><span className={d.status === 'healthy' ? 'ok' : 'bad'}>{d.status}</span></td>
                  </tr>
                ))}
                {!devices.length && (
                  <tr><td colSpan={4} className="small">No devices registered yet.</td></tr>
                )}
              </tbody>
            </table>
          </Card>

          {(isManager || isDispatcher) && (
          <Card title="Asset Types">
            <div className="type-grid">
              {typeSummary.map(item => (
                <div key={item.type} className="type-card">
                  <div className="type-title">{item.type}</div>
                  <div className="type-count">{item.count} assets</div>
                  <div className="type-meta">
                    <span>{item.active_alerts} alerts open</span>
                    <span>{item.avg_probability !== null ? `${(item.avg_probability*100).toFixed(1)}% avg risk` : 'No predictions'}</span>
                  </div>
                  <div className="type-locations">
                    {item.locations.map(loc => <StatBadge key={loc} label={loc} />)}
                  </div>
                </div>
              ))}
              {!typeSummary.length && <p className="small">No assets summarised yet.</p>}
            </div>
          </Card>
          )}

          {(isManager || isDispatcher) && (
          <Card title="Logistics Zones">
            <table className="table">
              <thead><tr><th>Location</th><th>Assets</th><th>Alerts</th></tr></thead>
              <tbody>
                {locationSummary.map(entry => (
                  <tr key={entry.location}>
                    <td>{entry.location}</td>
                    <td>{entry.devices}</td>
                    <td>{entry.active_alerts}</td>
                  </tr>
                ))}
                {!locationSummary.length && <tr><td colSpan={3} className="small">No locations reported.</td></tr>}
              </tbody>
            </table>
          </Card>
          )}
        </div>

        <div className="grid-2" style={{marginTop:24}}>
          {(isManager || isTechnician || isDispatcher) && (
          <Card title="Asset Detail">
            {selectedSnapshot ? (
              <div className="asset-detail">
                <div className="asset-header">
                  <h4>{selectedSnapshot.name}</h4>
                  <span className={`status-chip ${selectedSnapshot.status === 'healthy' ? 'ok' : 'bad'}`}>{selectedSnapshot.status}</span>
                </div>
                <p className="small">Type: {selectedSnapshot.type} | Location: {selectedSnapshot.location || 'Unassigned'}</p>
                <p className="small">Latest risk score: {selectedSnapshot.latest_probability !== null ? `${(selectedSnapshot.latest_probability*100).toFixed(1)}%` : 'Not available'}</p>
                <h5 className="asset-subheader">Most recent telemetry</h5>
                {renderLatestReading(latestReading)}
                <h5 className="asset-subheader">Open alerts</h5>
                {selectedSnapshot.open_alerts.length ? (
                  <ul className="reset">
                    {selectedSnapshot.open_alerts.map(alert => (
                      <li key={alert.id}><span className="pill">{alert.severity}</span> {alert.message}</li>
                    ))}
                  </ul>
                ) : <p className="small">No active alerts for this asset.</p>}
              </div>
            ) : <p className="small">Select an asset to review its health.</p>}
          </Card>
          )}

          {(isManager || isDispatcher) && (
          <Card title="Maintenance Recommendations">
            <ul className="reset">
              {recommendations.map(item => (
                <li key={`${item.device_id}-${item.timestamp}`}>
                  <b>{item.device_name}</b> ({item.type}) - {item.message}
                </li>
              ))}
              {!recommendations.length && <li>No predictive maintenance recommendations yet.</li>}
            </ul>
          </Card>
          )}
        </div>

        {(isManager || isTechnician) && (
        <div className="grid-2" style={{marginTop:24}}>
          <Card title="Maintenance Feedback">
            <div className="assistant-controls">
              <label htmlFor="feedback-outcome">Outcome</label>
              <input
                id="feedback-outcome"
                className="input"
                value={feedbackOutcome}
                onChange={e => setFeedbackOutcome(e.target.value)}
                placeholder="e.g., bearing replaced, inspection scheduled"
              />
              <label htmlFor="feedback-notes">Notes</label>
              <textarea
                id="feedback-notes"
                className="textarea"
                value={feedbackNotes}
                onChange={e => setFeedbackNotes(e.target.value)}
                placeholder="What actions were taken?"
              />
              <label htmlFor="feedback-submitted">Submitted by</label>
              <input
                id="feedback-submitted"
                className="input"
                value={feedbackSubmittedBy}
                onChange={e => setFeedbackSubmittedBy(e.target.value)}
                placeholder="technician@company.com"
              />
              <label htmlFor="feedback-probability">Related risk probability</label>
              <input
                id="feedback-probability"
                className="input"
                type="number"
                step="0.01"
                value={feedbackProbability}
                onChange={e => setFeedbackProbability(e.target.value)}
                placeholder={latestProbabilityValue !== undefined ? latestProbabilityValue.toFixed(2) : '0.50'}
              />
              {feedbackMessage && <p className="small">{feedbackMessage}</p>}
              <div>
                <button className="btn" onClick={submitFeedback} disabled={feedbackSaving}>
                  {feedbackSaving ? 'Saving...' : 'Record Feedback'}
                </button>
              </div>
              <div className="assistant-output">
                <p className="small">Recent outcomes for this asset:</p>
                {feedbackForDevice.length ? feedbackForDevice.slice(0,5).map(item => (
                  <p key={item.id}><b>{item.outcome}</b> - {item.notes || 'No notes'} <span className="small">({formatTime(item.created_at)})</span></p>
                )) : <p>No feedback logged yet.</p>}
              </div>
            </div>
          </Card>

          {renderAssistantActivityCard()}
        </div>
        )}

        {(isDispatcher && !isManager && !isTechnician) && (
          <div className="grid-2" style={{marginTop:24}}>
            {renderAssistantActivityCard()}
          </div>
        )}

        {(isManager || isTechnician) && (
        <div className="grid-2" style={{marginTop:24}}>
          <Card title="Telemetry (last 60 samples)">
            <div className="chart-container">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={historySeries} margin={{ left: 8, right: 16, top: 10, bottom: 4 }}>
                  <CartesianGrid stroke="#1f2c4d" strokeDasharray="4 4" />
                  <XAxis dataKey="timestamp" tickFormatter={formatTime} minTickGap={24} stroke="#67718a" />
                  <YAxis yAxisId="left" stroke="#67718a" tick={{ fill: '#67718a' }} domain={[0, 'auto']} />
                  <YAxis yAxisId="right" orientation="right" stroke="#67718a" tick={{ fill: '#67718a' }} domain={[0, 100]} />
                  <Tooltip labelFormatter={formatTime} formatter={(value, name) => [value, name]} contentStyle={{ background: '#101835', border: '1px solid #1d2849', color: '#fff' }} />
                  <Line yAxisId="left" type="monotone" dataKey="temperature" name="Temperature (C)" stroke="#5cc8ff" dot={false} strokeWidth={2} />
                  <Line yAxisId="left" type="monotone" dataKey="vibration" name="Vibration" stroke="#92f5c4" dot={false} strokeWidth={2} />
                  <Line yAxisId="right" type="monotone" dataKey="load_pct" name="Load %" stroke="#ff9f6b" dot={false} strokeWidth={2} strokeDasharray="5 5" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <Card title="Risk Trend">
            <div className="chart-container">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={riskSeries} margin={{ left: 8, right: 8, top: 10, bottom: 4 }}>
                  <defs>
                    <linearGradient id="risk" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#ff6b6b" stopOpacity={0.8} />
                      <stop offset="95%" stopColor="#ff6b6b" stopOpacity={0.05} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#1f2c4d" strokeDasharray="4 4" />
                  <XAxis dataKey="timestamp" tickFormatter={formatTime} minTickGap={24} stroke="#67718a" />
                  <YAxis domain={[0, 1]} tickFormatter={v => `${Math.round(v * 100)}%`} stroke="#67718a" />
                  <Tooltip labelFormatter={formatTime} formatter={value => [`${(value * 100).toFixed(1)}%`, 'Probability']} contentStyle={{ background: '#101835', border: '1px solid #1d2849', color: '#fff' }} />
                  <Area type="monotone" dataKey="probability" stroke="#ff6b6b" fill="url(#risk)" strokeWidth={2} dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </div>
        )}

        <div className="grid-2" style={{marginTop:24}}>
          <Card title="Live Feed">
            <div className="feed">
              <ul className="reset">
                {feed.map((f, idx) => (
                  <li key={idx}><code>{f.type}</code> - {f.data?.message || f.data?.temperature || ''} <span className="small">{f.data?.timestamp}</span></li>
                ))}
                {!feed.length && <li>No websocket events yet.</li>}
              </ul>
            </div>
          </Card>

          <Card title="What-If (Google AI)">
            <WhatIf
              deviceId={selectedDevice}
              baseline={latestReading}
              onPreview={handlePreview}
              loading={whatIfLoading}
              result={whatIfResult}
            />
          </Card>
        </div>

        {(isManager || isDispatcher) && (
        <div className="grid-2" style={{marginTop:24}}>
          <Card title="AI Operations Co-Pilot">
            <div className="assistant-controls">
              <label htmlFor="assistant-mode">Scenario</label>
              <select
                id="assistant-mode"
                className="select"
                value={assistantMode}
                onChange={e => setAssistantMode(e.target.value)}
              >
                {assistantModes.map(mode => (
                  <option key={mode.id} value={mode.id}>{mode.label}</option>
                ))}
              </select>
              {selectedAssistantMode && <p className="small">{selectedAssistantMode.description}</p>}
              {selectedAssistantMode?.requires_device && !selectedDevice && !assistantError && (
                <p className="warning">Select an asset above to provide context for this scenario.</p>
              )}
              {assistantError && <p className="warning">{assistantError}</p>}
              <label htmlFor="assistant-notes">Additional context (optional)</label>
              <textarea
                id="assistant-notes"
                className="textarea"
                value={assistantNotes}
                onChange={e => setAssistantNotes(e.target.value)}
                placeholder="Add symptoms, recent maintenance, or business constraints."
              />
              <div>
                <button className="btn" onClick={askAssistant} disabled={assistantLoading}>
                  {assistantLoading ? 'Thinking...' : 'Ask AI'}
                </button>
              </div>
              {assistantResponse && (
                <div className="assistant-output">
                  <p className="small">
                    Source: {assistantResponse.provider === 'google' ? 'Google Generative AI' : assistantResponse.provider === 'fallback' ? 'Local guidance' : 'Unavailable'}
                  </p>
                  {(assistantResponse.message || '').split(/\n+/).map((text, idx) => (
                    <p key={idx}>{text}</p>
                  ))}
                </div>
              )}
            </div>
          </Card>

          <Card title="Dispatch Notes">
            <ul className="reset">
              <li>Use the co-pilot to summarise incidents, plan technician checklists, and draft stakeholder updates.</li>
              <li>Gemini responses reflect the latest telemetry, predictions, and alerts gathered across the fleet.</li>
              <li>When AI is unavailable, the system falls back to conservative guidance so operations can continue.</li>
            </ul>
          </Card>
        </div>
        )}
      </div>
    </div>
  )
}

export default function App(){
  return <Dashboard />
}
