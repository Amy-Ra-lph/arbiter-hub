import React from "react";
import { EmptyState, EmptyStateBody } from "@patternfly/react-core";
import { ShieldAltIcon } from "@patternfly/react-icons";

const VulnerabilitiesTab: React.FC = () => {
  return (
    <EmptyState
      titleText="Vulnerability scanning not configured"
      icon={ShieldAltIcon}
      headingLevel="h4"
    >
      <EmptyStateBody>
        Connect a CVE data source to view workload vulnerability status.
      </EmptyStateBody>
    </EmptyState>
  );
};

export default VulnerabilitiesTab;
