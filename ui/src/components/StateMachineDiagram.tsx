import React from "react";
import { WorkloadState } from "src/utils/datatypes/globalDataTypes";

interface StateMachineDiagramProps {
  currentState: WorkloadState;
}

interface NodeDef {
  state: WorkloadState;
  x: number;
  y: number;
  color: string;
}

const NODES: NodeDef[] = [
  { state: WorkloadState.REGISTERED, x: 60, y: 40, color: "#2b9af3" },
  { state: WorkloadState.ATTESTING, x: 200, y: 40, color: "#009596" },
  { state: WorkloadState.HEALTHY, x: 340, y: 40, color: "#3e8635" },
  { state: WorkloadState.STALE, x: 340, y: 130, color: "#f0ab00" },
  { state: WorkloadState.FAILED, x: 200, y: 130, color: "#c9190b" },
  { state: WorkloadState.UNDER_REMEDIATION, x: 200, y: 220, color: "#a18fff" },
  { state: WorkloadState.REVOKED, x: 340, y: 220, color: "#8a8d90" },
];

const EDGES: [WorkloadState, WorkloadState][] = [
  [WorkloadState.REGISTERED, WorkloadState.ATTESTING],
  [WorkloadState.ATTESTING, WorkloadState.HEALTHY],
  [WorkloadState.ATTESTING, WorkloadState.FAILED],
  [WorkloadState.HEALTHY, WorkloadState.STALE],
  [WorkloadState.HEALTHY, WorkloadState.REVOKED],
  [WorkloadState.STALE, WorkloadState.ATTESTING],
  [WorkloadState.FAILED, WorkloadState.UNDER_REMEDIATION],
  [WorkloadState.FAILED, WorkloadState.REVOKED],
  [WorkloadState.UNDER_REMEDIATION, WorkloadState.ATTESTING],
];

const StateMachineDiagram: React.FC<StateMachineDiagramProps> = ({
  currentState,
}) => {
  const nodeMap = new Map(NODES.map((n) => [n.state, n]));

  return (
    <svg viewBox="0 0 440 280" width="440" height="280" aria-label="Workload state machine diagram">
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#6a6e73" />
        </marker>
      </defs>

      {EDGES.map(([from, to], i) => {
        const fromNode = nodeMap.get(from)!;
        const toNode = nodeMap.get(to)!;
        const dx = toNode.x - fromNode.x;
        const dy = toNode.y - fromNode.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        const r = 24;
        const sx = fromNode.x + (dx / dist) * r;
        const sy = fromNode.y + (dy / dist) * r;
        const ex = toNode.x - (dx / dist) * r;
        const ey = toNode.y - (dy / dist) * r;
        return (
          <line
            key={i}
            x1={sx}
            y1={sy}
            x2={ex}
            y2={ey}
            stroke="#6a6e73"
            strokeWidth="1.5"
            markerEnd="url(#arrow)"
          />
        );
      })}

      {NODES.map((node) => {
        const isCurrent = node.state === currentState;
        return (
          <g key={node.state}>
            <circle
              cx={node.x}
              cy={node.y}
              r={isCurrent ? 24 : 20}
              fill={isCurrent ? node.color : "transparent"}
              stroke={node.color}
              strokeWidth={isCurrent ? 3 : 2}
            />
            <text
              x={node.x}
              y={node.y + 36}
              textAnchor="middle"
              fontSize="10"
              fill="var(--pf-t--global--text--color--regular, #151515)"
            >
              {node.state.replace("_", " ")}
            </text>
          </g>
        );
      })}
    </svg>
  );
};

export default StateMachineDiagram;
