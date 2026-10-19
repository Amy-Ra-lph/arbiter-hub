import React, { useState, useEffect, useCallback } from "react";
import {
  Button,
  FormGroup,
  FormSelect,
  FormSelectOption,
  TextInput,
  TextArea,
  HelperText,
  HelperTextItem,
  ActionGroup,
  Card,
  CardBody,
  CardTitle,
  CardHeader,
  Tabs,
  Tab,
  TabTitleText,
  NumberInput,
  Switch,
} from "@patternfly/react-core";
import { PlusCircleIcon, TrashIcon } from "@patternfly/react-icons";

const KNOWN_ACTIONS = [
  "kbs_release",
  "request_reattest",
  "trigger_attestation",
  "register_workload",
  "revoke_workload",
  "remediate_workload",
  "sign_artifact",
  "verify_artifact",
];

const KNOWN_REQUIREMENTS = [
  { key: "workload_state", label: "Workload state", type: "select", options: ["healthy", "registered", "attesting", "stale", "failed", "under_remediation", "revoked"] },
  { key: "attestation_age_max", label: "Max attestation age (seconds)", type: "number" },
  { key: "caller_role", label: "Caller role", type: "select", options: ["attestation-admin", "attestation-operator", "attestation-pipeline", "attestation-viewer", "attestation-agent"] },
  { key: "caller_scope_includes_target", label: "Caller scope includes target", type: "boolean" },
  { key: "target_state", label: "Target state (any of)", type: "multi-select", options: ["healthy", "registered", "attesting", "stale", "failed", "under_remediation", "revoked"] },
];

interface Requirement {
  key: string;
  value: string | number | boolean | string[];
}

interface Rule {
  action: string;
  requirements: Requirement[];
}

interface PolicyBuilderProps {
  policyType: string;
  value: string;
  onChange: (json: string) => void;
  onJsonError: (err: string) => void;
}

function buildJson(rules: Rule[], obligations: string[]): string {
  const content: Record<string, unknown> = {
    rules: rules.map((r) => ({
      action: r.action,
      require: Object.fromEntries(
        r.requirements.map((req) => [req.key, req.value])
      ),
    })),
    obligations,
  };
  return JSON.stringify(content, null, 2);
}

function parseJson(json: string): { rules: Rule[]; obligations: string[] } | null {
  try {
    const parsed = JSON.parse(json);
    if (!parsed.rules || !Array.isArray(parsed.rules)) return null;
    const rules: Rule[] = parsed.rules.map(
      (r: { action?: string; require?: Record<string, unknown> }) => ({
        action: r.action ?? "",
        requirements: Object.entries(r.require ?? {}).map(([key, value]) => ({
          key,
          value: value as string | number | boolean | string[],
        })),
      })
    );
    const obligations: string[] = parsed.obligations ?? [];
    return { rules, obligations };
  } catch {
    return null;
  }
}

const PolicyBuilder: React.FC<PolicyBuilderProps> = ({
  policyType,
  value,
  onChange,
  onJsonError,
}) => {
  const [activeTab, setActiveTab] = useState(0);
  const [rules, setRules] = useState<Rule[]>([]);
  const [obligations, setObligations] = useState<string[]>([]);
  const [newObligation, setNewObligation] = useState("");
  const [rawJson, setRawJson] = useState(value);
  const [jsonErr, setJsonErr] = useState("");

  useEffect(() => {
    const parsed = parseJson(value);
    if (parsed) {
      setRules(parsed.rules);
      setObligations(parsed.obligations);
    }
    setRawJson(value);
  }, []);

  const syncToParent = useCallback(
    (r: Rule[], o: string[]) => {
      const json = buildJson(r, o);
      setRawJson(json);
      onChange(json);
      onJsonError("");
      setJsonErr("");
    },
    [onChange, onJsonError]
  );

  const addRule = () => {
    const updated = [...rules, { action: "", requirements: [] }];
    setRules(updated);
    syncToParent(updated, obligations);
  };

  const removeRule = (idx: number) => {
    const updated = rules.filter((_, i) => i !== idx);
    setRules(updated);
    syncToParent(updated, obligations);
  };

  const updateRuleAction = (idx: number, action: string) => {
    const updated = [...rules];
    updated[idx] = { ...updated[idx], action };
    setRules(updated);
    syncToParent(updated, obligations);
  };

  const addRequirement = (ruleIdx: number) => {
    const updated = [...rules];
    updated[ruleIdx] = {
      ...updated[ruleIdx],
      requirements: [
        ...updated[ruleIdx].requirements,
        { key: "", value: "" },
      ],
    };
    setRules(updated);
    syncToParent(updated, obligations);
  };

  const removeRequirement = (ruleIdx: number, reqIdx: number) => {
    const updated = [...rules];
    updated[ruleIdx] = {
      ...updated[ruleIdx],
      requirements: updated[ruleIdx].requirements.filter(
        (_, i) => i !== reqIdx
      ),
    };
    setRules(updated);
    syncToParent(updated, obligations);
  };

  const updateRequirement = (
    ruleIdx: number,
    reqIdx: number,
    field: "key" | "value",
    val: string | number | boolean | string[]
  ) => {
    const updated = [...rules];
    const req = { ...updated[ruleIdx].requirements[reqIdx] };

    if (field === "key") {
      req.key = val as string;
      const known = KNOWN_REQUIREMENTS.find((k) => k.key === val);
      if (known) {
        if (known.type === "number") req.value = 3600;
        else if (known.type === "boolean") req.value = true;
        else if (known.type === "multi-select") req.value = [];
        else if (known.type === "select") req.value = known.options?.[0] ?? "";
        else req.value = "";
      }
    } else {
      req.value = val;
    }

    updated[ruleIdx] = {
      ...updated[ruleIdx],
      requirements: updated[ruleIdx].requirements.map((r, i) =>
        i === reqIdx ? req : r
      ),
    };
    setRules(updated);
    syncToParent(updated, obligations);
  };

  const addObligation = () => {
    if (!newObligation.trim()) return;
    const updated = [...obligations, newObligation.trim()];
    setObligations(updated);
    setNewObligation("");
    syncToParent(rules, updated);
  };

  const removeObligation = (idx: number) => {
    const updated = obligations.filter((_, i) => i !== idx);
    setObligations(updated);
    syncToParent(rules, updated);
  };

  const handleRawJsonChange = (_evt: unknown, val: string) => {
    setRawJson(val);
    try {
      JSON.parse(val);
      setJsonErr("");
      onJsonError("");
      onChange(val);
      const parsed = parseJson(val);
      if (parsed) {
        setRules(parsed.rules);
        setObligations(parsed.obligations);
      }
    } catch {
      setJsonErr("Invalid JSON");
      onJsonError("Invalid JSON");
    }
  };

  const renderRequirementValue = (
    ruleIdx: number,
    reqIdx: number,
    req: Requirement
  ) => {
    const known = KNOWN_REQUIREMENTS.find((k) => k.key === req.key);

    if (known?.type === "select" && known.options) {
      return (
        <FormSelect
          value={req.value as string}
          onChange={(_evt, val) =>
            updateRequirement(ruleIdx, reqIdx, "value", val)
          }
          aria-label="Requirement value"
        >
          {known.options.map((o) => (
            <FormSelectOption key={o} value={o} label={o} />
          ))}
        </FormSelect>
      );
    }

    if (known?.type === "multi-select" && known.options) {
      const selected = (req.value as string[]) || [];
      return (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
          {known.options.map((o) => (
            <label key={o} style={{ display: "flex", alignItems: "center", gap: "4px", fontSize: "13px" }}>
              <input
                type="checkbox"
                checked={selected.includes(o)}
                onChange={(e) => {
                  const next = e.target.checked
                    ? [...selected, o]
                    : selected.filter((s) => s !== o);
                  updateRequirement(ruleIdx, reqIdx, "value", next);
                }}
              />
              {o}
            </label>
          ))}
        </div>
      );
    }

    if (known?.type === "number") {
      return (
        <NumberInput
          value={req.value as number}
          min={0}
          onMinus={() =>
            updateRequirement(
              ruleIdx,
              reqIdx,
              "value",
              Math.max(0, (req.value as number) - 60)
            )
          }
          onPlus={() =>
            updateRequirement(
              ruleIdx,
              reqIdx,
              "value",
              (req.value as number) + 60
            )
          }
          onChange={(evt) => {
            const v = Number((evt.target as HTMLInputElement).value);
            if (!isNaN(v)) updateRequirement(ruleIdx, reqIdx, "value", v);
          }}
          unit="sec"
          widthChars={6}
        />
      );
    }

    if (known?.type === "boolean") {
      return (
        <Switch
          id={`req-${ruleIdx}-${reqIdx}-val`}
          isChecked={req.value as boolean}
          onChange={(_evt, val) =>
            updateRequirement(ruleIdx, reqIdx, "value", val)
          }
          label="Yes"
        />
      );
    }

    return (
      <TextInput
        value={String(req.value)}
        onChange={(_evt, val) =>
          updateRequirement(ruleIdx, reqIdx, "value", val)
        }
        aria-label="Requirement value"
      />
    );
  };

  if (policyType !== "simple") {
    return (
      <FormGroup
        label="Policy Content (JSON)"
        isRequired
        fieldId="policy-content"
      >
        <TextArea
          id="policy-content"
          value={rawJson}
          onChange={handleRawJsonChange}
          rows={8}
          style={{ fontFamily: "monospace", fontSize: "13px" }}
        />
        {jsonErr && (
          <HelperText>
            <HelperTextItem variant="error">{jsonErr}</HelperTextItem>
          </HelperText>
        )}
      </FormGroup>
    );
  }

  return (
    <Tabs activeKey={activeTab} onSelect={(_evt, k) => setActiveTab(k as number)}>
      <Tab eventKey={0} title={<TabTitleText>Builder</TabTitleText>}>
        <div style={{ marginTop: "16px" }}>
          {rules.map((rule, ruleIdx) => (
            <Card key={ruleIdx} isCompact style={{ marginBottom: "12px" }}>
              <CardHeader
                actions={{
                  actions: (
                    <>
                      <Button
                        variant="plain"
                        aria-label="Remove rule"
                        onClick={() => removeRule(ruleIdx)}
                      >
                        <TrashIcon />
                      </Button>
                    </>
                  ),
                  hasNoOffset: true,
                }}
              >
                <CardTitle>Rule {ruleIdx + 1}</CardTitle>
              </CardHeader>
              <CardBody>
                <FormGroup label="Action" isRequired fieldId={`rule-${ruleIdx}-action`}>
                  <FormSelect
                    id={`rule-${ruleIdx}-action`}
                    value={rule.action}
                    onChange={(_evt, val) => updateRuleAction(ruleIdx, val)}
                  >
                    <FormSelectOption value="" label="Select action..." />
                    {KNOWN_ACTIONS.map((a) => (
                      <FormSelectOption key={a} value={a} label={a} />
                    ))}
                  </FormSelect>
                </FormGroup>

                <FormGroup label="Requirements" fieldId={`rule-${ruleIdx}-reqs`}>
                  {rule.requirements.map((req, reqIdx) => (
                    <div
                      key={reqIdx}
                      style={{
                        display: "grid",
                        gridTemplateColumns: "1fr 1fr auto",
                        gap: "8px",
                        marginBottom: "8px",
                        alignItems: "start",
                      }}
                    >
                      <FormSelect
                        value={req.key}
                        onChange={(_evt, val) =>
                          updateRequirement(ruleIdx, reqIdx, "key", val)
                        }
                        aria-label="Requirement key"
                      >
                        <FormSelectOption value="" label="Select..." />
                        {KNOWN_REQUIREMENTS.map((k) => (
                          <FormSelectOption
                            key={k.key}
                            value={k.key}
                            label={k.label}
                          />
                        ))}
                      </FormSelect>
                      {renderRequirementValue(ruleIdx, reqIdx, req)}
                      <Button
                        variant="plain"
                        aria-label="Remove requirement"
                        onClick={() => removeRequirement(ruleIdx, reqIdx)}
                      >
                        <TrashIcon />
                      </Button>
                    </div>
                  ))}
                  <Button
                    variant="link"
                    icon={<PlusCircleIcon />}
                    onClick={() => addRequirement(ruleIdx)}
                  >
                    Add requirement
                  </Button>
                </FormGroup>
              </CardBody>
            </Card>
          ))}

          <ActionGroup>
            <Button variant="secondary" icon={<PlusCircleIcon />} onClick={addRule}>
              Add Rule
            </Button>
          </ActionGroup>

          <FormGroup label="Obligations" fieldId="obligations" style={{ marginTop: "16px" }}>
            {obligations.map((ob, idx) => (
              <div
                key={idx}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  marginBottom: "4px",
                }}
              >
                <code style={{ flex: 1 }}>{ob}</code>
                <Button
                  variant="plain"
                  aria-label="Remove obligation"
                  onClick={() => removeObligation(idx)}
                >
                  <TrashIcon />
                </Button>
              </div>
            ))}
            <div style={{ display: "flex", gap: "8px", marginTop: "4px" }}>
              <TextInput
                value={newObligation}
                onChange={(_evt, val) => setNewObligation(val)}
                placeholder="e.g. log_to_rekor, notify_siem"
                aria-label="New obligation"
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addObligation(); } }}
              />
              <Button
                variant="link"
                icon={<PlusCircleIcon />}
                onClick={addObligation}
                isDisabled={!newObligation.trim()}
              >
                Add
              </Button>
            </div>
          </FormGroup>
        </div>
      </Tab>
      <Tab eventKey={1} title={<TabTitleText>JSON</TabTitleText>}>
        <div style={{ marginTop: "16px" }}>
          <TextArea
            value={rawJson}
            onChange={handleRawJsonChange}
            rows={12}
            style={{ fontFamily: "monospace", fontSize: "13px" }}
          />
          {jsonErr && (
            <HelperText>
              <HelperTextItem variant="error">{jsonErr}</HelperTextItem>
            </HelperText>
          )}
        </div>
      </Tab>
    </Tabs>
  );
};

export default PolicyBuilder;
