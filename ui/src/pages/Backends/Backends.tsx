import React from "react";
import {
  PageSection,
  Gallery,
  GalleryItem,
  Card,
  CardTitle,
  CardBody,
  EmptyState,
  EmptyStateBody,
  Icon,
  Button,
} from "@patternfly/react-core";
import {
  CheckCircleIcon,
  ExclamationCircleIcon,
  CubesIcon,
} from "@patternfly/react-icons";
import { Link } from "react-router-dom";
import TitleLayout from "src/components/layouts/TitleLayout";
import DataSpinner from "src/components/DataSpinner";
import { useGetBackendsQuery } from "src/services/rpcBackends";

const Backends: React.FC = () => {
  const { data: backends, isLoading } = useGetBackendsQuery(undefined, {
    pollingInterval: 30000,
  });

  if (isLoading) {
    return (
      <PageSection>
        <DataSpinner />
      </PageSection>
    );
  }

  const entries = backends ? Object.entries(backends) : [];

  return (
    <PageSection>
      <TitleLayout
        title="Backends"
        description="Attestation backend health and connectivity"
      />
      {entries.length === 0 ? (
        <EmptyState
          titleText="No backends configured"
          icon={CubesIcon}
          headingLevel="h4"
        >
          <EmptyStateBody>
            Configure attestation backends in the server configuration.
          </EmptyStateBody>
        </EmptyState>
      ) : (
        <Gallery hasGutter minWidths={{ default: "300px" }}>
          {entries.map(([name, info]) => (
            <GalleryItem key={name}>
              <Card>
                <CardTitle>
                  <Icon status={info.healthy ? "success" : "danger"}>
                    {info.healthy ? (
                      <CheckCircleIcon />
                    ) : (
                      <ExclamationCircleIcon />
                    )}
                  </Icon>{" "}
                  {name}
                </CardTitle>
                <CardBody>
                  <div>{info.detail}</div>
                  {info.last_check && (
                    <div style={{ marginTop: "8px", fontSize: "12px" }}>
                      Last check: {new Date(info.last_check).toLocaleString()}
                    </div>
                  )}
                  <div style={{ marginTop: "12px" }}>
                    <Link to={`/workloads?backend=${name}`}>
                      <Button variant="link" isInline>
                        View workloads →
                      </Button>
                    </Link>
                  </div>
                </CardBody>
              </Card>
            </GalleryItem>
          ))}
        </Gallery>
      )}
    </PageSection>
  );
};

export default Backends;
