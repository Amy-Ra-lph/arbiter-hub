import React from "react";
import {
  Button,
  Page,
  Masthead,
  MastheadMain,
  MastheadBrand,
  MastheadContent,
  PageSidebar,
  PageSidebarBody,
  SkipToContent,
  Toolbar,
  ToolbarContent,
  ToolbarItem,
} from "@patternfly/react-core";
import { Outlet } from "react-router-dom";
import Navigation from "src/navigation/Nav";
import ArbiterLogo from "src/components/ArbiterLogo";
import { useAuthContext } from "src/auth/OIDCProvider";

const AppLayout: React.FC = () => {
  const skipToContentRef = React.useRef<HTMLDivElement>(null);
  const { user, authMode, logout } = useAuthContext();

  const masthead = (
    <Masthead>
      <MastheadMain>
        <MastheadBrand>
          <ArbiterLogo />
        </MastheadBrand>
      </MastheadMain>
      <MastheadContent>
        <Toolbar>
          <ToolbarContent>
            <ToolbarItem align={{ default: "alignEnd" }}>
              <span style={{ fontSize: "14px", color: "var(--pf-t--global--text--color--subtle)" }}>
                Federation Attestation Hub
              </span>
            </ToolbarItem>
            {authMode === "oidc" && user && (
              <>
                <ToolbarItem>
                  <span style={{ fontSize: "14px" }}>{user}</span>
                </ToolbarItem>
                <ToolbarItem>
                  <Button variant="plain" onClick={logout}>
                    Log out
                  </Button>
                </ToolbarItem>
              </>
            )}
          </ToolbarContent>
        </Toolbar>
      </MastheadContent>
    </Masthead>
  );

  const sidebar = (
    <PageSidebar>
      <PageSidebarBody>
        <Navigation />
      </PageSidebarBody>
    </PageSidebar>
  );

  const skipToContent = (
    <SkipToContent href="#main-content-page-layout">
      Skip to content
    </SkipToContent>
  );

  return (
    <Page
      masthead={masthead}
      sidebar={sidebar}
      skipToContent={skipToContent}
      mainContainerId="main-content-page-layout"
    >
      <div ref={skipToContentRef}>
        <Outlet />
      </div>
    </Page>
  );
};

export default AppLayout;
