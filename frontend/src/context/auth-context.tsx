import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useNavigate } from "react-router-dom";

import { ApiError, SESSION_EXPIRED_EVENT, authApi, clearLegacyAccessToken, type User } from "@/lib/api";

interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (fullName: string, email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

/**
 * The session lives in httpOnly cookies the SPA cannot read, so "am I signed
 * in?" is answered by GET /auth/me. The API client refreshes an expired access
 * cookie on its own (once, single-flight) and fires SESSION_EXPIRED_EVENT when
 * the refresh cookie is rejected too.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  // StrictMode runs mount effects twice in development; ask /auth/me once.
  const startedRef = useRef(false);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    // Tokens from the old localStorage auth must not linger.
    clearLegacyAccessToken();

    authApi
      .me()
      .then((currentUser) => setUser(currentUser))
      .catch((error: unknown) => {
        // A 401 here means the refresh failed as well: signed out. A network
        // error, a 5xx or an aborted request must NOT sign the user out: no
        // logout call is made and the cookies stay, so a reload restores the
        // session once the API is reachable again.
        if (!(error instanceof ApiError && error.status === 401)) {
          console.warn("Could not check the session:", error);
        }
        setUser(null);
      })
      .finally(() => setIsLoading(false));
  }, []);

  // The refresh cookie was rejected mid-session: drop the user so
  // ProtectedRoute sends them back to the login page.
  useEffect(() => {
    const handleExpired = () => setUser(null);
    window.addEventListener(SESSION_EXPIRED_EVENT, handleExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, handleExpired);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    await authApi.login({ email, password });
    const currentUser = await authApi.me();
    setUser(currentUser);
  }, []);

  const signup = useCallback(async (fullName: string, email: string, password: string) => {
    await authApi.signup({ full_name: fullName, email, password });
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch (error) {
      // Sign out locally anyway; the cookies expire on their own.
      console.warn("Logout request failed:", error);
    }
    setUser(null);
    navigate("/login", { replace: true });
  }, [navigate]);

  const value = useMemo<AuthContextValue>(
    () => ({ user, isLoading, login, signup, logout }),
    [isLoading, user, login, signup, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
