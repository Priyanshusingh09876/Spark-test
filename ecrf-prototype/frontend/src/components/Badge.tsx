import type { ReactNode } from "react";
import type { Status, Verdict } from "../api/types";

export type BadgeKind = Status | Verdict | "pass" | "fail";

const VARIANTS: Record<BadgeKind, { cls: string; label: string }> = {
  exact: { cls: "badge-teal", label: "exact" },
  approximate: { cls: "badge-amber", label: "approximate" },
  rejected: { cls: "badge-rust", label: "rejected" },
  unchecked: { cls: "badge-draft", label: "unchecked" },
  flagged: { cls: "badge-amber", label: "flagged" },
  approved: { cls: "badge-teal", label: "approved" },
  draft: { cls: "badge-draft", label: "draft" },
  pass: { cls: "badge-teal", label: "PASS" },
  fail: { cls: "badge-rust", label: "FAIL" },
};

export default function Badge({ kind, children }: { kind: BadgeKind; children?: ReactNode }) {
  const v = VARIANTS[kind] ?? VARIANTS.draft;
  return <span className={`badge ${v.cls}`}>{children ?? v.label}</span>;
}
