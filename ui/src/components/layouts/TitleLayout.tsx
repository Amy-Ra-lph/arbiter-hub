import React from "react";
import { Content, ContentVariants } from "@patternfly/react-core";

interface TitleLayoutProps {
  title: string;
  description?: string;
}

const TitleLayout: React.FC<TitleLayoutProps> = ({ title, description }) => {
  return (
    <div style={{ marginBottom: "var(--pf-t--global--spacer--lg, 24px)" }}>
      <Content component={ContentVariants.h1}>{title}</Content>
      {description && (
        <Content component={ContentVariants.p}>{description}</Content>
      )}
    </div>
  );
};

export default TitleLayout;
