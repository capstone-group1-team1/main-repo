import React from "react";
import Head from "next/head";
import "../styles/globals.css";

export default function App({ Component, pageProps }) {
  return (
    <>
      <Head>
        <title>FacilityGraph AI</title>
        <meta name="description" content="Explainable Graph + RAG intelligence for facility maintenance." />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>
      <Component {...pageProps} />
    </>
  );
}
