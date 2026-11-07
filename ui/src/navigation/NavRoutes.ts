export interface NavItem {
  label: string;
  path: string;
}

export interface NavSection {
  label: string;
  items: NavItem[];
}

export const navSections: NavSection[] = [
  {
    label: "Dashboard",
    items: [{ label: "Dashboard", path: "/" }],
  },
  {
    label: "Attestation",
    items: [
      { label: "Workloads", path: "/workloads" },
      { label: "Backends", path: "/backends" },
      { label: "History", path: "/history" },
    ],
  },
  {
    label: "Policy",
    items: [
      { label: "Policies", path: "/policies" },
      { label: "KBS Secrets", path: "/kbs" },
    ],
  },
  {
    label: "Observability",
    items: [
      { label: "Events", path: "/events" },
      { label: "State Transitions", path: "/transitions" },
      { label: "Audit Log", path: "/audit" },
      { label: "Signals", path: "/signals" },
    ],
  },
  {
    label: "Vulnerabilities",
    items: [
      { label: "CVE Overview", path: "/vulnerabilities/cve" },
      { label: "Affected Workloads", path: "/vulnerabilities/workloads" },
    ],
  },
  {
    label: "Administration",
    items: [
      { label: "Federation", path: "/federation" },
      { label: "Remediation", path: "/remediation" },
    ],
  },
];
