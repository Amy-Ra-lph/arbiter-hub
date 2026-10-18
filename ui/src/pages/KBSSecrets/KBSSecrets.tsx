import React, { useState, useMemo } from "react";
import {
  PageSection,
  Toolbar,
  ToolbarContent,
  ToolbarItem,
  ToolbarGroup,
  Button,
  FormSelect,
  FormSelectOption,
  Modal,
  ModalVariant,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Form,
  FormGroup,
  TextInput,
  TextArea,
} from "@patternfly/react-core";
import {
  Table,
  Thead,
  Tr,
  Th,
  Tbody,
  Td,
} from "@patternfly/react-table";
import TitleLayout from "src/components/layouts/TitleLayout";
import SearchInputLayout from "src/components/layouts/SearchInputLayout";
import PaginationLayout from "src/components/layouts/PaginationLayout";
import StateBadge from "src/components/StateBadge";
import DataSpinner from "src/components/DataSpinner";
import { useGetKBSSecretsQuery, useStoreKBSSecretMutation } from "src/services/rpcKBS";
import { WorkloadState } from "src/utils/datatypes/globalDataTypes";

const KBSSecrets: React.FC = () => {
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(25);
  const [search, setSearch] = useState("");
  const [stateFilter, setStateFilter] = useState("");

  const [isStoreOpen, setIsStoreOpen] = useState(false);
  const [repo, setRepo] = useState("");
  const [secretType, setSecretType] = useState("");
  const [tag, setTag] = useState("");
  const [value, setValue] = useState("");
  const [requiredState, setRequiredState] = useState(WorkloadState.HEALTHY);
  const [workloadScope, setWorkloadScope] = useState("");

  const { data, isLoading } = useGetKBSSecretsQuery();
  const [storeSecret, { isLoading: storing }] = useStoreKBSSecretMutation();

  const items = data?.items ?? [];

  const filtered = useMemo(() => {
    let result = items;
    if (stateFilter) {
      result = result.filter((s) => s.required_state === stateFilter);
    }
    if (search) {
      const lower = search.toLowerCase();
      result = result.filter(
        (s) =>
          s.repo.toLowerCase().includes(lower) ||
          s.tag.toLowerCase().includes(lower)
      );
    }
    return result;
  }, [items, stateFilter, search]);

  const paginated = filtered.slice((page - 1) * perPage, page * perPage);

  const handleStore = async () => {
    await storeSecret({
      repo: repo.trim(),
      secret_type: secretType.trim(),
      tag: tag.trim(),
      value,
      required_state: requiredState,
      workload_scope: workloadScope.trim() || undefined,
    });
    resetForm();
    setIsStoreOpen(false);
  };

  const resetForm = () => {
    setRepo("");
    setSecretType("");
    setTag("");
    setValue("");
    setRequiredState(WorkloadState.HEALTHY);
    setWorkloadScope("");
  };

  if (isLoading) {
    return (
      <PageSection>
        <DataSpinner />
      </PageSection>
    );
  }

  return (
    <PageSection>
      <TitleLayout
        title="KBS Secrets"
        description="Key Broker Service secret store"
      />

      <Toolbar>
        <ToolbarContent>
          <ToolbarItem>
            <SearchInputLayout
              value={search}
              onChange={setSearch}
              placeholder="Search by repo or tag..."
            />
          </ToolbarItem>
          <ToolbarItem>
            <FormSelect
              value={stateFilter}
              onChange={(_evt, val) => setStateFilter(val)}
              aria-label="Filter by required state"
            >
              <FormSelectOption value="" label="All states" />
              {Object.values(WorkloadState).map((s) => (
                <FormSelectOption key={s} value={s} label={s.replace("_", " ")} />
              ))}
            </FormSelect>
          </ToolbarItem>
          <ToolbarGroup align={{ default: "alignEnd" }}>
            <ToolbarItem>
              <Button variant="primary" onClick={() => setIsStoreOpen(true)}>
                Store Secret
              </Button>
            </ToolbarItem>
          </ToolbarGroup>
          <ToolbarItem variant="pagination">
            <PaginationLayout
              itemCount={filtered.length}
              page={page}
              perPage={perPage}
              onSetPage={setPage}
              onPerPageSelect={(pp) => { setPerPage(pp); setPage(1); }}
            />
          </ToolbarItem>
        </ToolbarContent>
      </Toolbar>

      <Table aria-label="KBS Secrets">
        <Thead>
          <Tr>
            <Th>Repo</Th>
            <Th>Type</Th>
            <Th>Tag</Th>
            <Th>Required State</Th>
            <Th>Scope</Th>
            <Th>Created By</Th>
            <Th>Created</Th>
          </Tr>
        </Thead>
        <Tbody>
          {paginated.map((secret) => (
            <Tr key={secret.id}>
              <Td dataLabel="Repo">{secret.repo}</Td>
              <Td dataLabel="Type">{secret.secret_type}</Td>
              <Td dataLabel="Tag">{secret.tag}</Td>
              <Td dataLabel="Required State">
                <StateBadge state={secret.required_state} />
              </Td>
              <Td dataLabel="Scope">{secret.workload_scope ?? "all"}</Td>
              <Td dataLabel="Created By">{secret.created_by}</Td>
              <Td dataLabel="Created">
                {new Date(secret.created_at).toLocaleDateString()}
              </Td>
            </Tr>
          ))}
        </Tbody>
      </Table>

      <Modal
        isOpen={isStoreOpen}
        onClose={() => { resetForm(); setIsStoreOpen(false); }}
        variant={ModalVariant.medium}
      >
        <ModalHeader title="Store Secret" />
        <ModalBody>
          <Form>
            <FormGroup label="Repository" isRequired fieldId="secret-repo">
              <TextInput
                id="secret-repo"
                value={repo}
                onChange={(_evt, val) => setRepo(val)}
                placeholder="e.g. default"
              />
            </FormGroup>
            <FormGroup label="Secret Type" isRequired fieldId="secret-type">
              <TextInput
                id="secret-type"
                value={secretType}
                onChange={(_evt, val) => setSecretType(val)}
                placeholder="e.g. key, certificate"
              />
            </FormGroup>
            <FormGroup label="Tag" isRequired fieldId="secret-tag">
              <TextInput
                id="secret-tag"
                value={tag}
                onChange={(_evt, val) => setTag(val)}
              />
            </FormGroup>
            <FormGroup label="Value" isRequired fieldId="secret-value">
              <TextArea
                id="secret-value"
                value={value}
                onChange={(_evt, val) => setValue(val)}
                rows={4}
                style={{ fontFamily: "monospace" }}
              />
            </FormGroup>
            <FormGroup label="Required State" fieldId="secret-state">
              <FormSelect
                id="secret-state"
                value={requiredState}
                onChange={(_evt, val) => setRequiredState(val as WorkloadState)}
              >
                {Object.values(WorkloadState).map((s) => (
                  <FormSelectOption key={s} value={s} label={s.replace("_", " ")} />
                ))}
              </FormSelect>
            </FormGroup>
            <FormGroup label="Workload Scope" fieldId="secret-scope">
              <TextInput
                id="secret-scope"
                value={workloadScope}
                onChange={(_evt, val) => setWorkloadScope(val)}
                placeholder="Leave empty for all workloads"
              />
            </FormGroup>
          </Form>
        </ModalBody>
        <ModalFooter>
          <Button
            variant="primary"
            onClick={handleStore}
            isDisabled={
              !repo.trim() || !secretType.trim() || !tag.trim() || !value || storing
            }
          >
            Store Secret
          </Button>
          <Button variant="link" onClick={() => { resetForm(); setIsStoreOpen(false); }}>
            Cancel
          </Button>
        </ModalFooter>
      </Modal>
    </PageSection>
  );
};

export default KBSSecrets;
