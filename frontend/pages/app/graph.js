import React from "react";
import Head from "next/head";
import AppShell from "../../components/AppShell";
import GraphExplorer from "../../components/GraphExplorer";
export default function GraphPage(){return <><Head><title>Knowledge Graph · FacilityGraph AI</title></Head><AppShell title="Knowledge Graph" eyebrow="NEO4J OPERATIONAL CONTEXT"><GraphExplorer/></AppShell></>}
