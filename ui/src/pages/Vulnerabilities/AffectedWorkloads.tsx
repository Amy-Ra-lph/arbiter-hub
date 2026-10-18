import React from "react";
import { PageSection, EmptyState, EmptyStateBody } from "@patternfly/react-core";
import { ShieldAltIcon } from "@patternfly/react-icons";
import TitleLayout from "src/components/layouts/TitleLayout";

const AffectedWorkloads: React.FC = () => {
  return (
    <PageSection>
      <TitleLayout
        title="Affected Workloads"
        description="Workloads with known vulnerabilities"
      />
      <EmptyState
        titleText="No CVE data source connected"
        icon={ShieldAltIcon}
        headingLevel="h4"
      >
        <EmptyStateBody>
          Connect a CVE data source to map vulnerabilities to workloads.
        </EmptyStateBody>
      </EmptyState>
    </PageSection>
  );
};

export default AffectedWorkloads;
