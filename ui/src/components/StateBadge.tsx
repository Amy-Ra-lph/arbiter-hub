import React from "react";
import { Label } from "@patternfly/react-core";
import { WorkloadState } from "src/utils/datatypes/globalDataTypes";

const STATE_COLORS: Record<WorkloadState, "blue" | "teal" | "green" | "orange" | "red" | "purple" | "grey"> = {
  [WorkloadState.REGISTERED]: "blue",
  [WorkloadState.ATTESTING]: "teal",
  [WorkloadState.HEALTHY]: "green",
  [WorkloadState.STALE]: "orange",
  [WorkloadState.FAILED]: "red",
  [WorkloadState.UNDER_REMEDIATION]: "purple",
  [WorkloadState.REVOKED]: "grey",
};

interface StateBadgeProps {
  state: WorkloadState;
}

const StateBadge: React.FC<StateBadgeProps> = ({ state }) => {
  return (
    <Label color={STATE_COLORS[state]}>
      {state.replace("_", " ")}
    </Label>
  );
};

export default StateBadge;
