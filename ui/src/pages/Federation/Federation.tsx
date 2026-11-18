import React, { useEffect, useMemo, useState } from "react";
import {
  PageSection,
  Card,
  CardBody,
  CardTitle,
  DescriptionList,
  DescriptionListGroup,
  DescriptionListTerm,
  DescriptionListDescription,
  Flex,
  FlexItem,
  Label,
} from "@patternfly/react-core";
import {
  VisualizationProvider,
  VisualizationSurface,
  GraphComponent,
  DefaultNode,
  DefaultEdge,
  ModelKind,
  Visualization,
  ColaLayout,
  useVisualizationController,
} from "@patternfly/react-topology";
import type {
  Model,
  NodeModel,
  EdgeModel,
  ComponentFactory,
} from "@patternfly/react-topology";
import TitleLayout from "src/components/layouts/TitleLayout";
import StateBadge from "src/components/StateBadge";
import DataSpinner from "src/components/DataSpinner";
import { useGetWorkloadsQuery } from "src/services/rpcWorkloads";
import { useGetBackendsQuery } from "src/services/rpcBackends";
import { WorkloadState } from "src/utils/datatypes/globalDataTypes";

const STATE_COLORS: Record<WorkloadState, string> = {
  [WorkloadState.REGISTERED]: "#2b9af3",
  [WorkloadState.ATTESTING]: "#009596",
  [WorkloadState.HEALTHY]: "#3e8635",
  [WorkloadState.STALE]: "#f0ab00",
  [WorkloadState.FAILED]: "#c9190b",
  [WorkloadState.UNDER_REMEDIATION]: "#a18fff",
  [WorkloadState.REVOKED]: "#8a8d90",
};

const componentFactory: ComponentFactory = (kind, type) => {
  switch (type) {
    case "group":
      return DefaultNode;
    default:
      break;
  }
  switch (kind) {
    case ModelKind.graph:
      return GraphComponent;
    case ModelKind.node:
      return DefaultNode;
    case ModelKind.edge:
      return DefaultEdge;
    default:
      return undefined as never;
  }
};

function TopologyContent() {
  const controller = useVisualizationController();
  const [selectedId] = useState<string | null>(null);

  const { data: workloadsData, isLoading: wlLoading } = useGetWorkloadsQuery(
    { count: 100 },
    { pollingInterval: 30000 }
  );
  const { data: backendsData, isLoading: beLoading } = useGetBackendsQuery(
    undefined,
    { pollingInterval: 30000 }
  );

  const workloads = workloadsData?.items ?? [];
  const backends = backendsData ?? {};

  const model: Model = useMemo(() => {
    const nodes: NodeModel[] = [];
    const edges: EdgeModel[] = [];

    Object.entries(backends).forEach(([name, info]) => {
      nodes.push({
        id: `backend-${name}`,
        type: "node",
        label: name,
        width: 75,
        height: 75,
        data: {
          kind: "backend",
          name,
          healthy: info.healthy,
          detail: info.detail,
        },
        style: {
          fill: info.healthy ? "#3e8635" : "#c9190b",
        },
      });
    });

    workloads.forEach((w) => {
      nodes.push({
        id: `workload-${w.id}`,
        type: "node",
        label: w.display_name,
        width: 50,
        height: 50,
        data: {
          kind: "workload",
          workload: w,
        },
        style: {
          fill: STATE_COLORS[w.current_state] || "#8a8d90",
        },
      });

      edges.push({
        id: `edge-${w.id}`,
        type: "edge",
        source: `workload-${w.id}`,
        target: `backend-${w.backend_type}`,
      });
    });

    return {
      graph: {
        id: "federation-graph",
        type: "graph",
        layout: "Cola",
      },
      nodes,
      edges,
    };
  }, [workloads, backends]);

  useEffect(() => {
    controller.fromModel(model, false);
  }, [controller, model]);

  const selectedNode = useMemo(() => {
    if (!selectedId) return null;
    const nodeModel = model.nodes?.find((n) => n.id === selectedId);
    return nodeModel?.data ?? null;
  }, [selectedId, model]);

  if (wlLoading || beLoading) return <DataSpinner />;

  return (
    <Flex style={{ height: "600px" }}>
      <FlexItem grow={{ default: "grow" }} style={{ position: "relative" }}>
        <VisualizationSurface
          state={{ selectedIds: selectedId ? [selectedId] : [] }}
        />
      </FlexItem>
      {selectedNode && (
        <FlexItem style={{ width: "300px", padding: "16px" }}>
          <Card>
            <CardTitle>
              {selectedNode.kind === "backend"
                ? selectedNode.name
                : selectedNode.workload?.display_name}
            </CardTitle>
            <CardBody>
              {selectedNode.kind === "backend" ? (
                <DescriptionList>
                  <DescriptionListGroup>
                    <DescriptionListTerm>Health</DescriptionListTerm>
                    <DescriptionListDescription>
                      <Label
                        color={selectedNode.healthy ? "green" : "red"}
                      >
                        {selectedNode.healthy ? "healthy" : "unhealthy"}
                      </Label>
                    </DescriptionListDescription>
                  </DescriptionListGroup>
                  <DescriptionListGroup>
                    <DescriptionListTerm>Detail</DescriptionListTerm>
                    <DescriptionListDescription>
                      {selectedNode.detail}
                    </DescriptionListDescription>
                  </DescriptionListGroup>
                </DescriptionList>
              ) : (
                <DescriptionList>
                  <DescriptionListGroup>
                    <DescriptionListTerm>State</DescriptionListTerm>
                    <DescriptionListDescription>
                      <StateBadge
                        state={selectedNode.workload.current_state}
                      />
                    </DescriptionListDescription>
                  </DescriptionListGroup>
                  <DescriptionListGroup>
                    <DescriptionListTerm>Backend</DescriptionListTerm>
                    <DescriptionListDescription>
                      {selectedNode.workload.backend_type}
                    </DescriptionListDescription>
                  </DescriptionListGroup>
                  <DescriptionListGroup>
                    <DescriptionListTerm>Principal</DescriptionListTerm>
                    <DescriptionListDescription>
                      {selectedNode.workload.ipa_principal}
                    </DescriptionListDescription>
                  </DescriptionListGroup>
                </DescriptionList>
              )}
            </CardBody>
          </Card>
        </FlexItem>
      )}
    </Flex>
  );
}

const Federation: React.FC = () => {
  const controller = useMemo(() => {
    const vis = new Visualization();
    vis.registerComponentFactory(componentFactory);
    vis.registerLayoutFactory(
      (_type, graph) => new ColaLayout(graph, { layoutOnDrag: false })
    );
    return vis;
  }, []);

  return (
    <PageSection>
      <TitleLayout
        title="Federation Topology"
        description="Visual graph of workloads and their attestation backends"
      />

      <Flex style={{ marginBottom: "16px" }}>
        {Object.entries(STATE_COLORS).map(([state, color]) => (
          <FlexItem key={state}>
            <Label
              style={{
                backgroundColor: color,
                color: "#fff",
                borderColor: color,
              }}
            >
              {state.replace("_", " ")}
            </Label>
          </FlexItem>
        ))}
      </Flex>

      <VisualizationProvider controller={controller}>
        <TopologyContent />
      </VisualizationProvider>
    </PageSection>
  );
};

export default Federation;
