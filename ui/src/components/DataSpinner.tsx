import React from "react";
import { Bullseye, Spinner } from "@patternfly/react-core";

const DataSpinner: React.FC = () => {
  return (
    <Bullseye>
      <Spinner aria-label="Loading" />
    </Bullseye>
  );
};

export default DataSpinner;
