import { useCallback, useEffect, useRef, useState } from "react";
import { UserManager, type User } from "oidc-client-ts";

interface AuthConfig {
  auth_mode: string;
  issuer: string;
  client_id: string;
  scopes: string;
}

export interface AuthState {
  user: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  authMode: string;
  login: () => void;
  logout: () => void;
}

let _accessToken: string | null = null;

export function getStoredToken(): string | null {
  return _accessToken;
}

export function useAuth(): AuthState {
  const [isLoading, setIsLoading] = useState(true);
  const [user, setUser] = useState<string | null>(null);
  const [authMode, setAuthMode] = useState("dev");
  const managerRef = useRef<UserManager | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function init() {
      try {
        const resp = await fetch("/api/auth/config");
        const config: AuthConfig = await resp.json();

        if (cancelled) return;
        setAuthMode(config.auth_mode);

        if (config.auth_mode !== "oidc") {
          setUser("dev");
          _accessToken = null;
          setIsLoading(false);
          return;
        }

        const mgr = new UserManager({
          authority: config.issuer,
          client_id: config.client_id,
          redirect_uri: window.location.origin + "/",
          response_type: "code",
          scope: config.scopes,
          automaticSilentRenew: true,
        });

        managerRef.current = mgr;

        mgr.events.addAccessTokenExpired(() => {
          mgr.signinSilent().catch(() => mgr.signinRedirect());
        });

        mgr.events.addUserLoaded((u: User) => {
          _accessToken = u.access_token;
          setUser(u.profile?.preferred_username ?? u.profile?.sub ?? null);
        });

        const params = new URLSearchParams(window.location.search);
        if (params.has("code")) {
          const u = await mgr.signinCallback();
          if (u) {
            _accessToken = u.access_token;
            setUser(u.profile?.preferred_username ?? u.profile?.sub ?? null);
            window.history.replaceState({}, "", window.location.pathname);
          }
        } else {
          const u = await mgr.getUser();
          if (u && !u.expired) {
            _accessToken = u.access_token;
            setUser(u.profile?.preferred_username ?? u.profile?.sub ?? null);
          }
        }
      } catch {
        setUser(null);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    init();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(() => {
    managerRef.current?.signinRedirect();
  }, []);

  const logout = useCallback(() => {
    _accessToken = null;
    setUser(null);
    managerRef.current?.signoutRedirect();
  }, []);

  return {
    user,
    isAuthenticated: user !== null,
    isLoading,
    authMode,
    login,
    logout,
  };
}
