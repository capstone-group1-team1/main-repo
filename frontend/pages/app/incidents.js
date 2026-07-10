import React from "react";
import Head from "next/head";
import AppShell from "../../components/AppShell";
import IncidentsView from "../../components/IncidentsView";
export default function IncidentsPage(){return <><Head><title>Incidents · FacilityGraph AI</title></Head><AppShell title="Incidents" eyebrow="MAINTENANCE HISTORY"><IncidentsView/></AppShell></>}
