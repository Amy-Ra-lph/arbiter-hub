import React, { createContext, useContext } from "react";
import { Bullseye, Spinner } from "@patternfly/react-core";
import { useAuth, type AuthState } from "src/auth/useAuth";

const AuthContext = createContext<AuthState | null>(null);

export function useAuthContext(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuthContext must be inside OIDCProvider");
  return ctx;
}

export const OIDCProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const auth = useAuth();

  if (auth.isLoading) {
    return (
      <Bullseye>
        <Spinner size="xl" />
      </Bullseye>
    );
  }

  return <AuthContext.Provider value={auth}>{children}</AuthContext.Provider>;
};
