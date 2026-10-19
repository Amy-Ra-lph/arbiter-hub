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
  Label,
  Modal,
  ModalVariant,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Form,
  FormGroup,
  TextInput,
  Switch,
} from "@patternfly/react-core";
import {
  Table,
  Thead,
  Tr,
  Th,
  Tbody,
  Td,
  ExpandableRowContent,
} from "@patternfly/react-table";
import TitleLayout from "src/components/layouts/TitleLayout";
import SearchInputLayout from "src/components/layouts/SearchInputLayout";
import PaginationLayout from "src/components/layouts/PaginationLayout";
import DataSpinner from "src/components/DataSpinner";
import PolicyBuilder from "./PolicyBuilder";
import { useGetPoliciesQuery, useCreatePolicyMutation } from "src/services/rpcPolicies";

const Policies: React.FC = () => {
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(25);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [activeFilter, setActiveFilter] = useState("");
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const [isAddOpen, setIsAddOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newType, setNewType] = useState("simple");
  const [newScope, setNewScope] = useState("");
  const [newContent, setNewContent] = useState('{"rules":[],"obligations":[]}');
  const [newActive, setNewActive] = useState(true);
  const [jsonError, setJsonError] = useState("");

  const { data, isLoading } = useGetPoliciesQuery();
  const [createPolicy, { isLoading: creating }] = useCreatePolicyMutation();

  const items = data?.items ?? [];

  const policyTypes = useMemo(
    () => [...new Set(items.map((p) => p.policy_type))],
    [items]
  );

  const filtered = useMemo(() => {
    let result = items;
    if (typeFilter) result = result.filter((p) => p.policy_type === typeFilter);
    if (activeFilter === "active") result = result.filter((p) => p.active);
    if (activeFilter === "inactive") result = result.filter((p) => !p.active);
    if (search) {
      const lower = search.toLowerCase();
      result = result.filter((p) => p.name.toLowerCase().includes(lower));
    }
    return result;
  }, [items, typeFilter, activeFilter, search]);

  const paginated = filtered.slice((page - 1) * perPage, page * perPage);

  const toggleExpand = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleAdd = async () => {
    let content: Record<string, unknown>;
    try {
      content = JSON.parse(newContent);
    } catch {
      setJsonError("Invalid JSON");
      return;
    }
    await createPolicy({
      name: newName.trim(),
      policy_type: newType.trim(),
      scope: newScope.trim() || null,
      policy_content: content,
      active: newActive,
    });
    resetForm();
    setIsAddOpen(false);
  };

  const resetForm = () => {
    setNewName("");
    setNewType("simple");
    setNewScope("");
    setNewContent('{"rules":[],"obligations":[]}');
    setNewActive(true);
    setJsonError("");
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
        title="Policies"
        description="Attestation and access control policies"
      />

      <Toolbar>
        <ToolbarContent>
          <ToolbarItem>
            <SearchInputLayout
              value={search}
              onChange={setSearch}
              placeholder="Search by name..."
            />
          </ToolbarItem>
          <ToolbarItem>
            <FormSelect
              value={typeFilter}
              onChange={(_evt, val) => setTypeFilter(val)}
              aria-label="Filter by type"
            >
              <FormSelectOption value="" label="All types" />
              {policyTypes.map((t) => (
                <FormSelectOption key={t} value={t} label={t} />
              ))}
            </FormSelect>
          </ToolbarItem>
          <ToolbarItem>
            <FormSelect
              value={activeFilter}
              onChange={(_evt, val) => setActiveFilter(val)}
              aria-label="Filter by status"
            >
              <FormSelectOption value="" label="All statuses" />
              <FormSelectOption value="active" label="Active" />
              <FormSelectOption value="inactive" label="Inactive" />
            </FormSelect>
          </ToolbarItem>
          <ToolbarGroup align={{ default: "alignEnd" }}>
            <ToolbarItem>
              <Button variant="primary" onClick={() => setIsAddOpen(true)}>
                Add Policy
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

      <Table aria-label="Policies">
        <Thead>
          <Tr>
            <Th screenReaderText="Expand" />
            <Th>Name</Th>
            <Th>Type</Th>
            <Th>Scope</Th>
            <Th>Status</Th>
            <Th>Created By</Th>
            <Th>Created</Th>
          </Tr>
        </Thead>
        <Tbody>
          {paginated.map((policy, rowIndex) => {
            const isExpanded = expandedIds.has(policy.id);
            return (
              <React.Fragment key={policy.id}>
                <Tr>
                  <Td
                    expand={{
                      rowIndex,
                      isExpanded,
                      onToggle: () => toggleExpand(policy.id),
                    }}
                  />
                  <Td dataLabel="Name">{policy.name}</Td>
                  <Td dataLabel="Type">{policy.policy_type}</Td>
                  <Td dataLabel="Scope">{policy.scope ?? "global"}</Td>
                  <Td dataLabel="Status">
                    <Label color={policy.active ? "green" : "grey"}>
                      {policy.active ? "active" : "inactive"}
                    </Label>
                  </Td>
                  <Td dataLabel="Created By">{policy.created_by}</Td>
                  <Td dataLabel="Created">
                    {new Date(policy.created_at).toLocaleDateString()}
                  </Td>
                </Tr>
                {isExpanded && (
                  <Tr isExpanded>
                    <Td colSpan={7}>
                      <ExpandableRowContent>
                        <pre style={{ fontSize: "12px", whiteSpace: "pre-wrap" }}>
                          {JSON.stringify(policy.policy_content, null, 2)}
                        </pre>
                      </ExpandableRowContent>
                    </Td>
                  </Tr>
                )}
              </React.Fragment>
            );
          })}
        </Tbody>
      </Table>

      <Modal
        isOpen={isAddOpen}
        onClose={() => { resetForm(); setIsAddOpen(false); }}
        variant={ModalVariant.medium}
      >
        <ModalHeader title="Add Policy" />
        <ModalBody>
          <Form>
            <FormGroup label="Name" isRequired fieldId="policy-name">
              <TextInput
                id="policy-name"
                value={newName}
                onChange={(_evt, val) => setNewName(val)}
              />
            </FormGroup>
            <FormGroup label="Policy Type" isRequired fieldId="policy-type">
              <FormSelect
                id="policy-type"
                value={newType}
                onChange={(_evt, val) => {
                  setNewType(val);
                  if (val === "simple") {
                    setNewContent('{"rules":[],"obligations":[]}');
                  } else {
                    setNewContent("{}");
                  }
                  setJsonError("");
                }}
              >
                <FormSelectOption value="simple" label="simple — Rule-based (action + requirements)" />
                <FormSelectOption value="allowlist" label="allowlist — Approved value lists" />
                <FormSelectOption value="opa" label="opa — Open Policy Agent (Rego)" />
              </FormSelect>
            </FormGroup>
            <FormGroup label="Scope" fieldId="policy-scope">
              <TextInput
                id="policy-scope"
                value={newScope}
                onChange={(_evt, val) => setNewScope(val)}
                placeholder="Leave empty for global"
              />
            </FormGroup>
            <PolicyBuilder
              policyType={newType}
              value={newContent}
              onChange={setNewContent}
              onJsonError={setJsonError}
            />
            <FormGroup fieldId="policy-active">
              <Switch
                id="policy-active"
                label="Active"
                isChecked={newActive}
                onChange={(_evt, val) => setNewActive(val)}
              />
            </FormGroup>
          </Form>
        </ModalBody>
        <ModalFooter>
          <Button
            variant="primary"
            onClick={handleAdd}
            isDisabled={!newName.trim() || !!jsonError || creating}
          >
            Create Policy
          </Button>
          <Button variant="link" onClick={() => { resetForm(); setIsAddOpen(false); }}>
            Cancel
          </Button>
        </ModalFooter>
      </Modal>
    </PageSection>
  );
};

export default Policies;
