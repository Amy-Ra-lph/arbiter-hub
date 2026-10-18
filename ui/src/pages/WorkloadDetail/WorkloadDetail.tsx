import React, { useState } from "react";
import { useParams } from "react-router-dom";
import {
  PageSection,
  Content,
  ContentVariants,
  Tabs,
  Tab,
  TabTitleText,
  Button,
  Modal,
  ModalVariant,
  ModalHeader,
  ModalBody,
  ModalFooter,
  TextInput,
  FormGroup,
  Form,
  Flex,
  FlexItem,
  Alert,
} from "@patternfly/react-core";
import StateBadge from "src/components/StateBadge";
import DataSpinner from "src/components/DataSpinner";
import OverviewTab from "./OverviewTab";
import AttestationHistoryTab from "./AttestationHistoryTab";
import TransitionsTab from "./TransitionsTab";
import VulnerabilitiesTab from "./VulnerabilitiesTab";
import {
  useGetWorkloadQuery,
  useAttestWorkloadMutation,
  useRemediateWorkloadMutation,
  useRevokeWorkloadMutation,
} from "src/services/rpcWorkloads";
import { WorkloadState } from "src/utils/datatypes/globalDataTypes";

const CAN_ATTEST = new Set([
  WorkloadState.REGISTERED,
  WorkloadState.HEALTHY,
  WorkloadState.STALE,
  WorkloadState.UNDER_REMEDIATION,
]);

const CAN_REMEDIATE = new Set([WorkloadState.FAILED]);

const CAN_REVOKE = new Set([
  WorkloadState.HEALTHY,
  WorkloadState.FAILED,
]);

const WorkloadDetail: React.FC = () => {
  const { workloadId } = useParams<{ workloadId: string }>();
  const { data: workload, isLoading } = useGetWorkloadQuery(workloadId!);
  const [attestWorkload] = useAttestWorkloadMutation();
  const [remediateWorkload] = useRemediateWorkloadMutation();
  const [revokeWorkload] = useRevokeWorkloadMutation();

  const [activeTab, setActiveTab] = useState(0);
  const [isRemediateOpen, setIsRemediateOpen] = useState(false);
  const [isRevokeOpen, setIsRevokeOpen] = useState(false);
  const [justification, setJustification] = useState("");
  const [error, setError] = useState<string | null>(null);

  if (isLoading || !workload) {
    return (
      <PageSection>
        <DataSpinner />
      </PageSection>
    );
  }

  const handleAttest = async () => {
    try {
      await attestWorkload(workload.id).unwrap();
      setError(null);
    } catch (e) {
      setError(`Attestation failed: ${(e as { data?: { detail?: string } }).data?.detail ?? "unknown error"}`);
    }
  };

  const handleRemediate = async () => {
    try {
      await remediateWorkload({
        id: workload.id,
        justification: justification || undefined,
      }).unwrap();
      setError(null);
    } catch (e) {
      setError(`Remediation failed: ${(e as { data?: { detail?: string } }).data?.detail ?? "unknown error"}`);
    }
    setJustification("");
    setIsRemediateOpen(false);
  };

  const handleRevoke = async () => {
    try {
      await revokeWorkload({
        id: workload.id,
        justification,
      }).unwrap();
      setError(null);
    } catch (e) {
      setError(`Revocation failed: ${(e as { data?: { detail?: string } }).data?.detail ?? "unknown error"}`);
    }
    setJustification("");
    setIsRevokeOpen(false);
  };

  return (
    <PageSection>
      {error && (
        <Alert variant="danger" title={error} isInline actionClose={<Button variant="plain" onClick={() => setError(null)}>×</Button>} style={{ marginBottom: "16px" }} />
      )}
      <Flex>
        <FlexItem grow={{ default: "grow" }}>
          <Content component={ContentVariants.h1}>
            {workload.display_name}
          </Content>
          <Content component={ContentVariants.p}>
            {workload.ipa_principal}
          </Content>
        </FlexItem>
        <FlexItem>
          <StateBadge state={workload.current_state} />
        </FlexItem>
        <FlexItem>
          <Flex>
            {CAN_ATTEST.has(workload.current_state) && (
              <FlexItem>
                <Button variant="primary" onClick={handleAttest}>
                  Attest
                </Button>
              </FlexItem>
            )}
            {CAN_REMEDIATE.has(workload.current_state) && (
              <FlexItem>
                <Button
                  variant="secondary"
                  onClick={() => setIsRemediateOpen(true)}
                >
                  Remediate
                </Button>
              </FlexItem>
            )}
            {CAN_REVOKE.has(workload.current_state) && (
              <FlexItem>
                <Button
                  variant="danger"
                  onClick={() => setIsRevokeOpen(true)}
                >
                  Revoke
                </Button>
              </FlexItem>
            )}
          </Flex>
        </FlexItem>
      </Flex>

      <Tabs
        activeKey={activeTab}
        onSelect={(_evt, key) => setActiveTab(key as number)}
        style={{ marginTop: "16px" }}
      >
        <Tab eventKey={0} title={<TabTitleText>Overview</TabTitleText>}>
          <OverviewTab workload={workload} />
        </Tab>
        <Tab
          eventKey={1}
          title={<TabTitleText>Attestation History</TabTitleText>}
        >
          <AttestationHistoryTab workloadId={workload.id} />
        </Tab>
        <Tab eventKey={2} title={<TabTitleText>Transitions</TabTitleText>}>
          <TransitionsTab workloadId={workload.id} />
        </Tab>
        <Tab
          eventKey={3}
          title={<TabTitleText>Vulnerabilities</TabTitleText>}
        >
          <VulnerabilitiesTab />
        </Tab>
      </Tabs>

      <Modal
        isOpen={isRemediateOpen}
        onClose={() => setIsRemediateOpen(false)}
        variant={ModalVariant.small}
      >
        <ModalHeader title="Remediate Workload" />
        <ModalBody>
          <Form>
            <FormGroup label="Justification" fieldId="remediate-justification">
              <TextInput
                id="remediate-justification"
                value={justification}
                onChange={(_evt, val) => setJustification(val)}
                placeholder="Optional justification..."
              />
            </FormGroup>
          </Form>
        </ModalBody>
        <ModalFooter>
          <Button variant="primary" onClick={handleRemediate}>
            Remediate
          </Button>
          <Button variant="link" onClick={() => setIsRemediateOpen(false)}>
            Cancel
          </Button>
        </ModalFooter>
      </Modal>

      <Modal
        isOpen={isRevokeOpen}
        onClose={() => setIsRevokeOpen(false)}
        variant={ModalVariant.small}
      >
        <ModalHeader title="Revoke Workload" />
        <ModalBody>
          <Form>
            <FormGroup
              label="Justification"
              isRequired
              fieldId="revoke-justification"
            >
              <TextInput
                id="revoke-justification"
                value={justification}
                onChange={(_evt, val) => setJustification(val)}
                placeholder="Required justification..."
              />
            </FormGroup>
          </Form>
        </ModalBody>
        <ModalFooter>
          <Button
            variant="danger"
            onClick={handleRevoke}
            isDisabled={!justification.trim()}
          >
            Revoke
          </Button>
          <Button variant="link" onClick={() => setIsRevokeOpen(false)}>
            Cancel
          </Button>
        </ModalFooter>
      </Modal>
    </PageSection>
  );
};

export default WorkloadDetail;
