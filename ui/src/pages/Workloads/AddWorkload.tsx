import React, { useState } from "react";
import {
  Form,
  FormGroup,
  TextInput,
  FormSelect,
  FormSelectOption,
} from "@patternfly/react-core";
import ModalWithFormLayout from "src/components/layouts/ModalWithFormLayout";
import { useCreateWorkloadMutation } from "src/services/rpcWorkloads";
import { WorkloadType, BackendType } from "src/utils/datatypes/globalDataTypes";

interface AddWorkloadProps {
  isOpen: boolean;
  onClose: () => void;
}

const AddWorkload: React.FC<AddWorkloadProps> = ({ isOpen, onClose }) => {
  const [displayName, setDisplayName] = useState("");
  const [ipaPrincipal, setIpaPrincipal] = useState("");
  const [workloadType, setWorkloadType] = useState(WorkloadType.SERVICE);
  const [backendType, setBackendType] = useState(BackendType.KEYLIME);
  const [staleTtl, setStaleTtl] = useState("3600");

  const [createWorkload, { isLoading }] = useCreateWorkloadMutation();

  const canSubmit = displayName.trim() !== "" && ipaPrincipal.trim() !== "";

  const handleSubmit = async () => {
    if (!canSubmit) return;
    try {
      await createWorkload({
        display_name: displayName.trim(),
        ipa_principal: ipaPrincipal.trim(),
        workload_type: workloadType,
        backend_type: backendType,
        stale_ttl_seconds: Number(staleTtl) || 3600,
      }).unwrap();
      resetForm();
      onClose();
    } catch {
      // RTK Query caches the error state on the mutation; modal stays open
    }
  };

  const resetForm = () => {
    setDisplayName("");
    setIpaPrincipal("");
    setWorkloadType(WorkloadType.SERVICE);
    setBackendType(BackendType.KEYLIME);
    setStaleTtl("3600");
  };

  const handleClose = () => {
    resetForm();
    onClose();
  };

  return (
    <ModalWithFormLayout
      title="Register Workload"
      isOpen={isOpen}
      onClose={handleClose}
      onSubmit={handleSubmit}
      submitLabel="Register Workload"
      isSubmitDisabled={!canSubmit || isLoading}
    >
      <Form>
        <FormGroup label="Display Name" isRequired fieldId="display-name">
          <TextInput
            id="display-name"
            value={displayName}
            onChange={(_evt, val) => setDisplayName(val)}
            aria-label="Display Name"
          />
        </FormGroup>
        <FormGroup label="IPA Principal" isRequired fieldId="ipa-principal">
          <TextInput
            id="ipa-principal"
            value={ipaPrincipal}
            onChange={(_evt, val) => setIpaPrincipal(val)}
            placeholder="host/fqdn@REALM"
            aria-label="IPA Principal"
          />
        </FormGroup>
        <FormGroup label="Workload Type" fieldId="workload-type">
          <FormSelect
            id="workload-type"
            value={workloadType}
            onChange={(_evt, val) => setWorkloadType(val as WorkloadType)}
          >
            {Object.values(WorkloadType).map((t) => (
              <FormSelectOption key={t} value={t} label={t} />
            ))}
          </FormSelect>
        </FormGroup>
        <FormGroup label="Backend" fieldId="backend-type">
          <FormSelect
            id="backend-type"
            value={backendType}
            onChange={(_evt, val) => setBackendType(val as BackendType)}
          >
            {Object.values(BackendType).map((t) => (
              <FormSelectOption key={t} value={t} label={t} />
            ))}
          </FormSelect>
        </FormGroup>
        <FormGroup label="Stale TTL (seconds)" fieldId="stale-ttl">
          <TextInput
            id="stale-ttl"
            type="number"
            value={staleTtl}
            onChange={(_evt, val) => setStaleTtl(val)}
          />
        </FormGroup>
      </Form>
    </ModalWithFormLayout>
  );
};

export default AddWorkload;
