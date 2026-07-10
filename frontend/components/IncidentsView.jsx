import React, { useEffect, useState } from "react";
import { useWorkspace } from "./AppShell";

export default function IncidentsView() {
  const { api, session, showError } = useWorkspace();
  const [incidents, setIncidents] = useState([]);
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ device_id:"", problem:"", resolution:"", technician:session.profile?.fullName || session.name });
  const canCreate = session.role === "technician" || session.role === "admin";
  const names = Object.fromEntries(devices.map((item)=>[item.asset_id,item.device_name]));

  async function load() { setLoading(true); try { const [i,d] = await Promise.all([api.listIncidents(session.userId), api.listDevices(session.userId)]); setIncidents(i); setDevices(d); if (!form.device_id && d[0]) setForm((current)=>({...current,device_id:d[0].asset_id})); } catch(error) { showError(error.reason); } finally { setLoading(false); } }
  useEffect(()=>{ load(); },[session.userId]);
  async function submit(event) { event.preventDefault(); setSaving(true); try { await api.createIncident(form,session.userId); setForm({...form,problem:"",resolution:""}); await load(); } catch(error) { showError(error.reason); } finally { setSaving(false); } }

  return <div className="incidents-layout"><section className="panel data-panel"><div className="panel-heading"><div><span className="kicker">MAINTENANCE HISTORY</span><h2>Incident intelligence</h2></div><span className="count-pill">{incidents.length} records</span></div><div className="table-scroll"><table><thead><tr><th>Incident ID</th><th>Device</th><th>Severity</th><th>Status</th><th>Date</th><th>Summary</th></tr></thead><tbody>{loading?<tr><td colSpan="6"><div className="table-empty"><span className="spinner"/>Loading incidents…</div></td></tr>:incidents.map((incident)=><tr key={incident.incident_id}><td className="mono strong">{incident.incident_id}</td><td><b>{names[incident.device_id] || incident.device_id}</b><small className="cell-sub">{incident.device_id}</small></td><td><span className="neutral-tag">Not recorded</span></td><td><span className={`status-badge ${incident.status}`}><i/>{incident.status}</span></td><td>{incident.date}</td><td className="summary-cell">{incident.problem}</td></tr>)}</tbody></table></div><p className="data-note">Severity is not part of the current backend incident schema, so it is shown as not recorded.</p></section>
    <aside className="panel incident-form"><div className="panel-heading"><div><span className="kicker">SUPPORTED WRITE ACTION</span><h2>Log an incident</h2></div></div>{canCreate?<form onSubmit={submit}><label htmlFor="device">Device</label><select id="device" value={form.device_id} onChange={(e)=>setForm({...form,device_id:e.target.value})}>{devices.map((d)=><option key={d.asset_id} value={d.asset_id}>{d.asset_id} · {d.device_name}</option>)}</select><label htmlFor="problem">Problem</label><textarea id="problem" rows="4" value={form.problem} onChange={(e)=>setForm({...form,problem:e.target.value})} placeholder="Describe the observed issue" minLength="3" required/><label htmlFor="resolution">Resolution <span>optional</span></label><textarea id="resolution" rows="3" value={form.resolution} onChange={(e)=>setForm({...form,resolution:e.target.value})} placeholder="Leave blank while open"/><label htmlFor="technician">Technician</label><input id="technician" value={form.technician} onChange={(e)=>setForm({...form,technician:e.target.value})} required/><button className="button button-accent button-full" disabled={saving}>{saving?"Saving…":"Log incident"}</button><small>Creates the incident in Neo4j and queues evidence ingestion through the existing backend workflow.</small></form>:<div className="permission-card"><span>♙</span><h3>View-only access</h3><p>Operators can inspect incident history. Logging incidents is available to technician and admin demo roles.</p></div>}</aside>
  </div>;
}
