import React from "react";
import {
  Grid,
  GridItem,
  Card,
  CardBody,
  DescriptionList,
  DescriptionListGroup,
  DescriptionListTerm,
  DescriptionListDescription,
} from "@patternfly/react-core";
import StateMachineDiagram from "src/components/StateMachineDiagram";
import TTLCountdown from "src/components/TTLCountdown";
import type { Workload } from "src/utils/datatypes/globalDataTypes";

interface OverviewTabProps {
  workload: Workload;
}

const OverviewTab: React.FC<OverviewTabProps> = ({ workload }) => {
  return (
    <Grid hasGutter>
      <GridItem span={6}>
        <Card>
          <CardBody>
            <DescriptionList>
              <DescriptionListGroup>
                <DescriptionListTerm>Workload Type</DescriptionListTerm>
                <DescriptionListDescription>
                  {workload.workload_type}
                </DescriptionListDescription>
              </DescriptionListGroup>
              <DescriptionListGroup>
                <DescriptionListTerm>Backend</DescriptionListTerm>
                <DescriptionListDescription>
                  {workload.backend_type}
                </DescriptionListDescription>
              </DescriptionListGroup>
              <DescriptionListGroup>
                <DescriptionListTerm>Registered</DescriptionListTerm>
                <DescriptionListDescription>
                  {new Date(workload.registered_at).toLocaleString()}
                </DescriptionListDescription>
              </DescriptionListGroup>
              <DescriptionListGroup>
                <DescriptionListTerm>Last Attested</DescriptionListTerm>
                <DescriptionListDescription>
                  {workload.last_attested_at
                    ? new Date(workload.last_attested_at).toLocaleString()
                    : "Never"}
                </DescriptionListDescription>
              </DescriptionListGroup>
              <DescriptionListGroup>
                <DescriptionListTerm>TTL Remaining</DescriptionListTerm>
                <DescriptionListDescription>
                  <TTLCountdown
                    lastAttestedAt={workload.last_attested_at}
                    staleTtlSeconds={workload.stale_ttl_seconds}
                  />
                </DescriptionListDescription>
              </DescriptionListGroup>
              <DescriptionListGroup>
                <DescriptionListTerm>Stale TTL</DescriptionListTerm>
                <DescriptionListDescription>
                  {workload.stale_ttl_seconds}s
                </DescriptionListDescription>
              </DescriptionListGroup>
              {Object.entries(workload.metadata).map(([k, v]) => (
                <DescriptionListGroup key={k}>
                  <DescriptionListTerm>{k}</DescriptionListTerm>
                  <DescriptionListDescription>
                    {typeof v === "object" ? JSON.stringify(v) : String(v)}
                  </DescriptionListDescription>
                </DescriptionListGroup>
              ))}
            </DescriptionList>
          </CardBody>
        </Card>
      </GridItem>
      <GridItem span={6}>
        <Card>
          <CardBody>
            <StateMachineDiagram currentState={workload.current_state} />
          </CardBody>
        </Card>
      </GridItem>
    </Grid>
  );
};

export default OverviewTab;
