import React from "react";
import Head from "next/head";
import AppShell from "../../components/AppShell";
import DeviceExplorer from "../../components/DeviceExplorer";
export default function DevicesPage(){return <><Head><title>Devices · FacilityGraph AI</title></Head><AppShell title="Devices" eyebrow="CONNECTED ASSET INVENTORY"><DeviceExplorer/></AppShell></>}
