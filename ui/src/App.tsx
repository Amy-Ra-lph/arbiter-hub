import React from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import AppLayout from "src/AppLayout";
import Dashboard from "src/pages/Dashboard/Dashboard";
import Workloads from "src/pages/Workloads/Workloads";
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
          <Route path="/workloads/:workloadId" element={<Placeholder name="Workload Detail" />} />
          <Route path="/backends" element={<Placeholder name="Backends" />} />
          <Route path="/history" element={<Placeholder name="History" />} />
          <Route path="/vulnerabilities/cve" element={<Placeholder name="CVE Overview" />} />
          <Route path="/vulnerabilities/workloads" element={<Placeholder name="Affected Workloads" />} />
          <Route path="/policies" element={<Placeholder name="Policies" />} />
          <Route path="/policies/:policyId" element={<Placeholder name="Policy Detail" />} />
          <Route path="/kbs" element={<Placeholder name="KBS Secrets" />} />
          <Route path="/audit" element={<Placeholder name="Audit Log" />} />
          <Route path="/federation" element={<Placeholder name="Federation" />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
};

export default App;
