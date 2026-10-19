import React, { useEffect } from "react";
import { Outlet } from "react-router-dom";
import {
  Button,
  EmptyState,
  EmptyStateBody,
  PageSection,
} from "@patternfly/react-core";
import { useAuthContext } from "src/auth/OIDCProvider";
import { isLoggedOut, clearLoggedOut } from "src/auth/useAuth";

export const ProtectedRoute: React.FC = () => {
  const { isAuthenticated, authMode, login } = useAuthContext();

  const loginTriggered = React.useRef(false);
  useEffect(() => {
    if (authMode === "oidc" && !isAuthenticated && !isLoggedOut() && !loginTriggered.current) {
      loginTriggered.current = true;
      login();
    }
  }, [authMode, isAuthenticated, login]);

  if (authMode === "oidc" && !isAuthenticated) {
    if (isLoggedOut()) {
      return (
        <PageSection>
          <EmptyState titleText="Logged out" headingLevel="h2">
            <EmptyStateBody>
              You have been logged out of Arbiter Hub. Your Kerberos
              session remains active. Run <code>kdestroy</code> to
              fully end your session.
            </EmptyStateBody>
            <Button
              variant="primary"
              onClick={() => {
                clearLoggedOut();
                login();
              }}
            >
              Log in again
            </Button>
          </EmptyState>
        </PageSection>
      );
    }
    return null;
  }

  return <Outlet />;
};
