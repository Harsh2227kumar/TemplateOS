import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { ApiError, authApi, type User } from "@/lib/api";
import {
  SESSION_EXPIRED_EVENT,
  clearAccessToken,
  getAccessToken,
  setAccessToken,
} from "@/lib/auth-token";

interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (fullName: string, email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => getAccessToken() || null);
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let active = true;
    if (!token) {
      setUser(null);
      setIsLoading(false);
      return () => {
        active = false;
      };
    }

    setIsLoading(true);
    authApi
      .me(token)
      .then((currentUser) => {
        if (active) setUser(currentUser);
      })
      .catch((error: unknown) => {
        // Only a 401 means the token is bad. A network error, a 5xx or a
        // request aborted by a page reload must not sign the user out.
        if (error instanceof ApiError && error.status === 401) {
          clearAccessToken();
          if (active) setToken(null);
        }
        if (active) setUser(null);
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });

    return () => {
      active = false;
    };
  }, [token]);

  // Any API call rejected with 401 means the token expired or was revoked:
  // sign out so ProtectedRoute sends the user back to the login page.
  useEffect(() => {
    const handleExpired = () => {
      clearAccessToken();
      setToken(null);
      setUser(null);
    };
    window.addEventListener(SESSION_EXPIRED_EVENT, handleExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, handleExpired);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isLoading,
      login: async (email, password) => {
        const result = await authApi.login({ email, password });
        const currentUser = await authApi.me(result.access_token);
        setAccessToken(result.access_token);
        setToken(result.access_token);
        setUser(currentUser);
      },
      signup: async (fullName, email, password) => {
        await authApi.signup({ full_name: fullName, email, password });
      },
      logout: () => {
        clearAccessToken();
        setToken(null);
        setUser(null);
      },
    }),
    [isLoading, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
