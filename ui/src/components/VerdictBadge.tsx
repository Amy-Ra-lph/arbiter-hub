import React from "react";
import { Label } from "@patternfly/react-core";
import { AttestationVerdict } from "src/utils/datatypes/globalDataTypes";

const VERDICT_COLORS: Record<AttestationVerdict, "green" | "red" | "yellow" | "grey"> = {
  [AttestationVerdict.PASS]: "green",
  [AttestationVerdict.FAIL]: "red",
  [AttestationVerdict.ERROR]: "yellow",
  [AttestationVerdict.UNAVAILABLE]: "grey",
};

interface VerdictBadgeProps {
  verdict: AttestationVerdict;
}

const VerdictBadge: React.FC<VerdictBadgeProps> = ({ verdict }) => {
  return <Label color={VERDICT_COLORS[verdict]}>{verdict}</Label>;
};

export default VerdictBadge;
