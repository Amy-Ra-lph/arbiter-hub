import React, { useEffect } from "react";
import { Outlet } from "react-router-dom";
import { useAuthContext } from "src/auth/OIDCProvider";

export const ProtectedRoute: React.FC = () => {
  const { isAuthenticated, authMode, login } = useAuthContext();

  useEffect(() => {
    if (authMode === "oidc" && !isAuthenticated) {
      login();
    }
  }, [authMode, isAuthenticated, login]);

  if (authMode === "oidc" && !isAuthenticated) {
    return null;
  }

  return <Outlet />;
};
