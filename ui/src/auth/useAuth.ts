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
let _loggedOut = false;

export function isLoggedOut(): boolean {
  return _loggedOut;
}

export function clearLoggedOut(): void {
  _loggedOut = false;
}

export function getStoredToken(): string | null {
  return _accessToken;
}

export function useAuth(): AuthState {
  const [isLoading, setIsLoading] = useState(true);
  const [user, setUser] = useState<string | null>(null);
  const [authMode, setAuthMode] = useState("dev");
  const managerRef = useRef<UserManager | null>(null);
  const configRef = useRef<AuthConfig | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function init() {
      try {
        const resp = await fetch("/api/auth/config");
        const config: AuthConfig = await resp.json();

        if (cancelled) return;
        configRef.current = config;
        setAuthMode(config.auth_mode);

        if (config.auth_mode !== "oidc") {
          setUser("dev");
          _accessToken = null;
          setIsLoading(false);
          return;
        }

        const scopes = config.scopes.includes("offline_access")
          ? config.scopes
          : config.scopes + " offline_access";

        const mgr = new UserManager({
          authority: config.issuer,
          client_id: config.client_id,
          redirect_uri: window.location.origin + "/",
          response_type: "code",
          scope: scopes,
          automaticSilentRenew: true,
          accessTokenExpiringNotificationTimeInSeconds: 120,
        });

        managerRef.current = mgr;

        mgr.events.addAccessTokenExpired(() => {
          mgr.signinSilent().catch(() => {
            loginViaForm(config);
          });
        });

        mgr.events.addUserLoaded((u: User) => {
          _accessToken = u.access_token;
          setUser(u.profile?.preferred_username ?? u.profile?.sub ?? null);
        });

        const params = new URLSearchParams(window.location.search);
        if (params.has("code")) {
          try {
            const u = await mgr.signinCallback();
            if (u) {
              _accessToken = u.access_token;
              setUser(
                u.profile?.preferred_username ?? u.profile?.sub ?? null
              );
              window.history.replaceState({}, "", window.location.pathname);
            }
          } catch {
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
    const mgr = managerRef.current;
    const config = configRef.current;
    if (mgr) {
      mgr.signinRedirect().catch(() => {
        if (config) loginViaForm(config);
      });
    } else if (config) {
      loginViaForm(config);
    }
  }, []);

  const logout = useCallback(() => {
    _accessToken = null;
    _loggedOut = true;
    setUser(null);
    managerRef.current?.removeUser();
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

function loginViaForm(config: AuthConfig): void {
  const authorizeParams = new URLSearchParams({
    response_type: "code",
    client_id: config.client_id,
    redirect_uri: window.location.origin + "/",
    scope: config.scopes,
  });
  const loginUrl =
    config.issuer +
    "/ui/auth/login?return_to=" +
    encodeURIComponent("/idp/authorize?" + authorizeParams.toString());
  window.location.href = loginUrl;
}
