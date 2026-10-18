import React from "react";
import { PageSection, EmptyState, EmptyStateBody } from "@patternfly/react-core";
import { ShieldAltIcon } from "@patternfly/react-icons";
import TitleLayout from "src/components/layouts/TitleLayout";

const CveOverview: React.FC = () => {
  return (
    <PageSection>
      <TitleLayout title="CVE Overview" description="Vulnerability monitoring" />
      <EmptyState
        titleText="Vulnerability monitoring coming soon"
        icon={ShieldAltIcon}
        headingLevel="h4"
      >
        <EmptyStateBody>
          Connect a CVE data source to monitor vulnerabilities across your
          federation workloads.
        </EmptyStateBody>
      </EmptyState>
    </PageSection>
  );
};

export default CveOverview;
