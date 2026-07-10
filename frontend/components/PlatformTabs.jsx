import React, { useState } from "react";

const content = [
  { tab: "Knowledge Graph", tag: "CONNECTED CONTEXT", heading: "Understand every asset through its operational context.", copy: "Traverse real relationships between devices, rooms, dependencies, incidents, and replacement history.", cards: [["⌘","Asset Relationships","See how connected devices interact."],["□","Room Context","Place every asset in its operational space."],["↗","Dependency Mapping","Trace upstream and downstream effects."],["↺","Replacement History","Follow lifecycle links across asset changes."]] },
  { tab: "Maintenance RAG", tag: "RETRIEVED EVIDENCE", heading: "Search manuals and maintenance evidence with AI.", copy: "Retrieve relevant technical content through semantic search and keep every answer tied to its source.", cards: [["⇩","PDF Ingestion","Bring maintenance manuals into retrieval."],["¶","Semantic Chunking","Split documents around meaningful context."],["◎","Weaviate Retrieval","Find relevant evidence by meaning."],["✓","Grounded Answers","Connect generated guidance to citations."]] },
  { tab: "Incident Intelligence", tag: "HISTORICAL CONTEXT", heading: "Turn maintenance history into faster decisions.", copy: "Use previous problems and resolutions as evidence alongside the device graph and manuals.", cards: [["≋","Similar Incident Search","Retrieve related maintenance problems."],["✓","Previous Resolutions","Review what worked in earlier cases."],["◷","Device History","Understand incidents across an asset lifecycle."],["♙","Technician Context","Preserve the human record behind a fix."]] },
];

export default function PlatformTabs() {
  const [active, setActive] = useState(0);
  const item = content[active];
  return <div className="platform-tabs"><div className="tab-list" role="tablist" aria-label="Platform capabilities">{content.map((entry,index)=><button key={entry.tab} role="tab" aria-selected={active===index} onClick={()=>setActive(index)}><span>0{index+1}</span>{entry.tab}<i>→</i></button>)}</div><div className="tab-content" role="tabpanel"><span className="kicker">{item.tag}</span><h3>{item.heading}</h3><p>{item.copy}</p><div className="tab-card-grid">{item.cards.map(([icon,title,copy])=><article key={title}><i>{icon}</i><h4>{title}</h4><p>{copy}</p></article>)}</div></div></div>;
}
