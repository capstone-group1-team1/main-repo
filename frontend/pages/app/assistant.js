import React from "react";
import Head from "next/head";
import AppShell, { useWorkspace } from "../../components/AppShell";
import ChatWindow from "../../components/ChatWindow";
function Assistant(){const {api,session}=useWorkspace();return <ChatWindow ask={(question)=>api.ask(question,session.userId)}/>}
export default function AssistantPage(){return <><Head><title>AI Assistant · FacilityGraph AI</title></Head><AppShell title="AI Assistant" eyebrow="GRAPH + RAG COPILOT"><Assistant/></AppShell></>}
