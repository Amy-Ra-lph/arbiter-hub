import React from "react";
import {
  PageSection,
  Content,
  ContentVariants,
} from "@patternfly/react-core";

const Dashboard: React.FC = () => {
  return (
    <PageSection>
      <Content component={ContentVariants.h1}>Dashboard</Content>
      <Content component={ContentVariants.p}>
        Attestation estate overview — coming in Task 4.
      </Content>
    </PageSection>
  );
};

export default Dashboard;
