"""
graph_retriever.py — the GRAPH branch.  ALL query-time Cypher lives here as
named, parameterized traversals (question text never enters a query string).

Each returned GraphFact carries:
  - path_str : the serialized graph path — this IS the citation
  - text     : a readable sentence for the LLM prompt
  - source_chunk_id (Layer-2 enrichment facts only) : manual-page provenance
"""

from __future__ import annotations

from app.core.config import get_neo4j_driver, get_settings
from app.models.schemas import GraphFact, GraphNeighborhood, GraphEdge, GraphSignals
from app.router.entity_matcher import MatchedEntity


def _facts_for_device(session, asset_id: str) -> list[GraphFact]:
    facts: list[GraphFact] = []
    settings = get_settings()

    # 1) Direct structural relationships (1 hop, both directions).
    rows = session.run(
        """MATCH (d:Device {asset_id:$id})-[r:CONTAINS|CONNECTED_TO|CONTROLS|USES]-(o)
           RETURN d.asset_id AS a, type(r) AS rel, coalesce(o.asset_id,o.name) AS b,
                  coalesce(o.device_name,o.name) AS b_name,
                  startNode(r).asset_id AS start_id""",
        id=asset_id,
    ).data()
    for i, r in enumerate(rows):
        left, right = (r["a"], r["b"]) if r["start_id"] == r["a"] else (r["b"], r["a"])
        path = f"{left} —{r['rel']}→ {right}"
        facts.append(
            GraphFact(
                fact_id=f"gf-{asset_id}-{i}",
                path_str=path,
                text=f"{left} {r['rel'].replace('_',' ').lower()} {right} ({r['b_name']}).",
                device_id=asset_id,
                hop_count=1,
            )
        )

    # 2) Upstream dependency chain (what this device depends on, 2 hops):
    rows = session.run(
        """MATCH p=(d:Device {asset_id:$id})<-[:CONTROLS|CONNECTED_TO*1..2]-(up:Device)
           WHERE up.status='Active'
           RETURN [n IN nodes(p) | n.asset_id] AS chain, length(p) AS hops
           LIMIT $lim""",
        id=asset_id,
        lim=settings.graph_neighbor_limit,
    ).data()
    for i, r in enumerate(rows):
        chain = " ← ".join(r["chain"])
        facts.append(
            GraphFact(
                fact_id=f"gd-{asset_id}-{i}",
                path_str=chain,
                text=f"Dependency chain: {chain} (upstream devices that "
                f"{asset_id} relies on).",
                device_id=asset_id,
                hop_count=r["hops"],
            )
        )

    # 3) Incident history.
    rows = session.run(
        """MATCH (d:Device {asset_id:$id})-[:HAS_INCIDENT]->(i:Incident)
           RETURN i.incident_id AS id, toString(i.date) AS date,
                  i.problem AS p, i.resolution AS res, i.status AS st
           ORDER BY i.date DESC LIMIT $lim""",
        id=asset_id,
        lim=settings.graph_incident_limit,
    ).data()
    for r in rows:
        facts.append(
            GraphFact(
                fact_id=f"gi-{r['id']}",
                path_str=f"{asset_id} —HAS_INCIDENT→ {r['id']}",
                text=f"Incident {r['id']} ({r['date']}, {r['st']}): {r['p']} — "
                f"resolution: {r['res']}.",
                device_id=asset_id,
                hop_count=1,
            )
        )

    # 4) Lifecycle: install/retire dates + replacement chain.
    rows = session.run(
        """MATCH (d:Device {asset_id:$id})
           OPTIONAL MATCH (d)-[rb:REPLACED_BY]->(n:Device)
           OPTIONAL MATCH (o:Device)-[ro:REPLACED_BY]->(d)
           RETURN toString(d.installed_on) AS inst, toString(d.retired_on) AS ret,
                  d.status AS st, n.asset_id AS next, o.asset_id AS prev""",
        id=asset_id,
    ).data()
    for r in rows:
        txt = f"{asset_id} was installed on {r['inst']} (status: {r['st']}"
        if r["ret"]:
            txt += f", retired on {r['ret']}"
        txt += ")."
        if r["next"]:
            txt += f" It was replaced by {r['next']}."
        if r["prev"]:
            txt += f" It replaced {r['prev']}."
        facts.append(
            GraphFact(
                fact_id=f"gl-{asset_id}",
                path_str=f"{asset_id} lifecycle",
                text=txt,
                device_id=asset_id,
                hop_count=1,
            )
        )

    # 5) Layer-2 enrichment: symptom -> procedure facts (with provenance).
    rows = session.run(
        """MATCH (s:Symptom {device_id:$id})-[r:RESOLVED_BY]->(pr:Procedure)
           RETURN s.name AS s, pr.name AS p, r.source_chunk_id AS src
           LIMIT $lim""",
        id=asset_id,
        lim=settings.graph_enrichment_limit,
    ).data()
    for i, r in enumerate(rows):
        facts.append(
            GraphFact(
                fact_id=f"ge-{asset_id}-{i}",
                path_str=f"Symptom '{r['s']}' —RESOLVED_BY→ Procedure '{r['p']}'",
                text=f"Known resolution for '{r['s']}' on {asset_id}: {r['p']}.",
                device_id=asset_id,
                hop_count=1,
                source_chunk_id=r["src"],
            )
        )
    return facts


def _facts_for_room(session, room: str) -> list[GraphFact]:
    """CONTAINS over ALL devices ever in the room — the temporal query.
    Retired devices are included with their date window, which is exactly
    what makes 'what was installed last year?' answerable."""
    rows = session.run(
        """MATCH (r:Room {name:$room})-[:CONTAINS]->(d:Device)
           RETURN d.asset_id AS id, d.device_name AS name, d.status AS st,
                  toString(d.installed_on) AS inst, toString(d.retired_on) AS ret
           ORDER BY d.installed_on""",
        room=room,
    ).data()
    facts = []
    for r in rows:
        window = f"installed {r['inst']}" + (
            f", retired {r['ret']}" if r["ret"] else ", still active"
        )
        facts.append(
            GraphFact(
                fact_id=f"gr-{room}-{r['id']}",
                path_str=f"{room} —CONTAINS→ {r['id']}",
                text=f"{room} contains {r['id']} ({r['name']}), status {r['st']}, {window}.",
                device_id=r["id"],
                hop_count=1,
            )
        )
    return facts


def retrieve(
    question: str, entities: list[MatchedEntity]
) -> tuple[list[GraphFact], GraphSignals]:
    facts: list[GraphFact] = []
    exact = False
    with get_neo4j_driver().session() as s:
        for e in entities:
            exact = True
            if e.kind == "device":
                facts += _facts_for_device(s, e.canonical_id)
            else:
                facts += _facts_for_room(s, e.canonical_id)
        if not entities:
            # No entity matched: give the office topology overview so the
            # LLM has *something*, but GraphSignals will mark this weak.
            rows = s.run("""MATCH (r:Room)-[:CONTAINS]->(d:Device {status:'Active'})
                   RETURN r.name AS room, collect(d.asset_id) AS devices""").data()
            for r in rows:
                facts.append(
                    GraphFact(
                        fact_id=f"gt-{r['room']}",
                        path_str=f"{r['room']} —CONTAINS→ {', '.join(r['devices'])}",
                        text=f"{r['room']} contains: {', '.join(r['devices'])}.",
                        hop_count=2,
                        matched_exactly=False,
                    )
                )

    # De-duplicate by fact_id (overlapping entities — e.g. a device and its
    # room — can surface the same fact twice), preserving first-seen order.
    seen: set[str] = set()
    unique: list[GraphFact] = []
    for f in facts:
        if f.fact_id in seen:
            continue
        seen.add(f.fact_id)
        unique.append(f)

    signals = GraphSignals(
        any_exact_entity_match=exact,
        min_hop_count=min((f.hop_count for f in unique), default=99),
        fact_count=len(unique),
    )
    return unique[: get_settings().graph_max_facts], signals


# --- endpoint helpers -------------------------------------------------------


def get_device_info(asset_id: str) -> dict | None:
    with get_neo4j_driver().session() as s:
        row = s.run(
            """MATCH (d:Device {asset_id:$id})
                       RETURN d {.*, installed_on: toString(d.installed_on),
                                  retired_on: toString(d.retired_on),
                                  warranty_expiry: toString(d.warranty_expiry)}
                       AS d""",
            id=asset_id,
        ).single()
        if row is None:
            return None
        rels = s.run(
            """MATCH (d:Device {asset_id:$id})-[r]-(o)
               RETURN type(r) AS rel, startNode(r)=d AS out,
                      coalesce(o.asset_id, o.name, o.document_id) AS other""",
            id=asset_id,
        ).data()
        rel_strs = [
            (
                f"{asset_id} —{r['rel']}→ {r['other']}"
                if r["out"]
                else f"{r['other']} —{r['rel']}→ {asset_id}"
            )
            for r in rels
        ]
        return {"device": row["d"], "relationships": rel_strs}


def get_neighborhood(asset_id: str) -> GraphNeighborhood:
    with get_neo4j_driver().session() as s:
        rows = s.run(
            """MATCH (d:Device {asset_id:$id})-[r]-(o)
               WHERE NOT o:Component
               RETURN coalesce(o.asset_id,o.name,o.document_id,o.incident_id) AS oid,
                      labels(o)[0] AS label,
                      coalesce(o.device_name,o.name,o.problem,'') AS oname,
                      type(r) AS rel, startNode(r).asset_id = $id AS outgoing""",
            id=asset_id,
        ).data()
    nodes = [{"id": asset_id, "label": "Device", "name": asset_id}]
    edges = []
    seen = {asset_id}
    for r in rows:
        if r["oid"] not in seen:
            nodes.append({"id": r["oid"], "label": r["label"], "name": r["oname"]})
            seen.add(r["oid"])
        src, tgt = (asset_id, r["oid"]) if r["outgoing"] else (r["oid"], asset_id)
        edges.append(GraphEdge(source=src, relation=r["rel"], target=tgt))
    return GraphNeighborhood(nodes=nodes, edges=edges)
