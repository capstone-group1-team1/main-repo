import React, { useEffect, useMemo, useState } from "react";
import { useWorkspace } from "./AppShell";

export default function DeviceExplorer() {
  const { api, session, showError } = useWorkspace();
  const [devices, setDevices] = useState([]);
  const [incidents, setIncidents] = useState([]);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([api.listDevices(session.userId), api.listIncidents(session.userId)])
      .then(([deviceRows, incidentRows]) => { setDevices(deviceRows); setIncidents(incidentRows); })
      .catch((error) => showError(error.reason)).finally(() => setLoading(false));
  }, [session.userId]);

  const incidentCounts = useMemo(() => incidents.reduce((counts, item) => ({ ...counts, [item.device_id]: (counts[item.device_id] || 0) + 1 }), {}), [incidents]);
  async function open(id) { try { setSelected(await api.getDevice(id, session.userId)); } catch (error) { showError(error.reason); } }

  return <div className="data-layout"><section className="panel data-panel"><div className="panel-heading"><div><span className="kicker">ASSET INVENTORY</span><h2>Connected devices</h2></div><span className="count-pill">{devices.length} devices</span></div><div className="table-scroll"><table><thead><tr><th>Asset ID</th><th>Name</th><th>Type / model</th><th>Vendor</th><th>Room</th><th>Status</th><th>Incidents</th><th><span className="sr-only">Action</span></th></tr></thead><tbody>{loading ? <tr><td colSpan="8"><div className="table-empty"><span className="spinner" />Loading devices…</div></td></tr> : devices.map((device)=><tr key={device.asset_id}><td className="mono strong">{device.asset_id}</td><td><b>{device.device_name}</b></td><td>{device.model || "—"}</td><td>{device.manufacturer || "—"}</td><td>{device.room}</td><td><span className={`status-badge ${String(device.status).toLowerCase()}`}><i />{device.status}</span></td><td>{incidentCounts[device.asset_id] || 0}</td><td><button className="row-action" onClick={()=>open(device.asset_id)} aria-label={`View ${device.device_name} graph and details`}>Graph ↗</button></td></tr>)}</tbody></table></div></section>
    <aside className="panel detail-panel"><div className="panel-heading"><div><span className="kicker">GRAPH DETAILS</span><h2>Asset context</h2></div></div>{selected ? <div className="device-detail"><div className="detail-title"><span>▱</span><div><h3>{selected.device_name}</h3><p>{selected.asset_id} · {selected.model}</p></div></div><dl><div><dt>Manufacturer</dt><dd>{selected.manufacturer}</dd></div><div><dt>Room</dt><dd>{selected.room}</dd></div><div><dt>Firmware</dt><dd>{selected.firmware_version}</dd></div><div><dt>Installed</dt><dd>{selected.installation_date || "Not recorded"}</dd></div><div><dt>Warranty</dt><dd>{selected.warranty_expiry || "Not recorded"}</dd></div><div><dt>Serial</dt><dd className="mono">{selected.serial_number}</dd></div></dl><h4>Direct relationships <span>{selected.relationships.length}</span></h4><div className="relationship-list">{selected.relationships.length ? selected.relationships.map((item,index)=><div key={index}><i>⌘</i><span>{item}</span></div>) : <p>No relationships returned.</p>}</div></div> : <div className="empty-compact large"><span>⌘</span><h3>Select a connected asset</h3><p>Open a device to inspect backend detail and its Neo4j relationships.</p></div>}</aside>
  </div>;
}
