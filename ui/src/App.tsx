import React from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import AppLayout from "src/AppLayout";
import Dashboard from "src/pages/Dashboard/Dashboard";
import Workloads from "src/pages/Workloads/Workloads";
import WorkloadDetail from "src/pages/WorkloadDetail/WorkloadDetail";
import Backends from "src/pages/Backends/Backends";
import History from "src/pages/History/History";
import Policies from "src/pages/Policies/Policies";
import KBSSecrets from "src/pages/KBSSecrets/KBSSecrets";
import AuditLog from "src/pages/AuditLog/AuditLog";
import CveOverview from "src/pages/Vulnerabilities/CveOverview";
import AffectedWorkloads from "src/pages/Vulnerabilities/AffectedWorkloads";
import { PageSection, Content, ContentVariants } from "@patternfly/react-core";

const Placeholder: React.FC<{ name: string }> = ({ name }) => (
  <PageSection>
    <Content component={ContentVariants.h1}>{name}</Content>
    <Content component={ContentVariants.p}>Coming soon.</Content>
  </PageSection>
);

const App: React.FC = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<Dashboard />} />
          <Route path="/workloads" element={<Workloads />} />
          <Route path="/workloads/:workloadId" element={<WorkloadDetail />} />
          <Route path="/backends" element={<Backends />} />
          <Route path="/history" element={<History />} />
          <Route path="/vulnerabilities/cve" element={<CveOverview />} />
          <Route path="/vulnerabilities/workloads" element={<AffectedWorkloads />} />
          <Route path="/policies" element={<Policies />} />
          <Route path="/policies/:policyId" element={<Placeholder name="Policy Detail" />} />
          <Route path="/kbs" element={<KBSSecrets />} />
          <Route path="/audit" element={<AuditLog />} />
          <Route path="/federation" element={<Placeholder name="Federation" />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
};

export default App;
