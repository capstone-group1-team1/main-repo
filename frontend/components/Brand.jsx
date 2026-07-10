import React from "react";
import Link from "next/link";

export function LogoMark({ compact = false }) {
  return (
    <Link href="/" className={`brand ${compact ? "brand-compact" : ""}`} aria-label="FacilityGraph AI home">
      <span className="brand-mark" aria-hidden="true">
        <i /><i /><i /><i />
      </span>
      {!compact && <span>FacilityGraph <b>AI</b></span>}
    </Link>
  );
}

export function ArrowIcon() {
  return <span aria-hidden="true">↗</span>;
}
