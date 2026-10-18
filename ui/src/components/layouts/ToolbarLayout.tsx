import React from "react";
import {
  Toolbar,
  ToolbarContent,
  ToolbarItem,
} from "@patternfly/react-core";

interface ToolbarLayoutProps {
  children: React.ReactNode;
}

const ToolbarLayout: React.FC<ToolbarLayoutProps> = ({ children }) => {
  return (
    <Toolbar>
      <ToolbarContent>
        {React.Children.map(children, (child) => (
          <ToolbarItem>{child}</ToolbarItem>
        ))}
      </ToolbarContent>
    </Toolbar>
  );
};

export default ToolbarLayout;
