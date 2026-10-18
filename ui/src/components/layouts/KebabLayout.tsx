import React, { useState } from "react";
import {
  Dropdown,
  DropdownItem,
  DropdownList,
  MenuToggle,
} from "@patternfly/react-core";
import { EllipsisVIcon } from "@patternfly/react-icons";

export interface KebabAction {
  label: string;
  onClick: () => void;
  isDisabled?: boolean;
  isDanger?: boolean;
}

interface KebabLayoutProps {
  actions: KebabAction[];
}

const KebabLayout: React.FC<KebabLayoutProps> = ({ actions }) => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <Dropdown
      isOpen={isOpen}
      onSelect={() => setIsOpen(false)}
      onOpenChange={setIsOpen}
      toggle={(toggleRef) => (
        <MenuToggle
          ref={toggleRef}
          variant="plain"
          onClick={() => setIsOpen(!isOpen)}
          isExpanded={isOpen}
          aria-label="Actions"
        >
          <EllipsisVIcon />
        </MenuToggle>
      )}
      popperProps={{ position: "right" }}
    >
      <DropdownList>
        {actions.map((action) => (
          <DropdownItem
            key={action.label}
            onClick={action.onClick}
            isDisabled={action.isDisabled}
            isDanger={action.isDanger}
          >
            {action.label}
          </DropdownItem>
        ))}
      </DropdownList>
    </Dropdown>
  );
};

export default KebabLayout;
