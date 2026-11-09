import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { useAuth } from "@/context/auth-context";
import { ApiError } from "@/lib/api";

/** EKLINK_REDIRECT_URI: EkLink sends the browser here with ?code=&state=. */
export function EklinkCallbackPage() {
  const { loginWithEklink } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [error, setError] = useState("");
  // The code is single-use; StrictMode runs effects twice in development.
  const startedRef = useRef(false);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;

    const code = searchParams.get("code");
    const state = searchParams.get("state");
    if (!code || !state) {
      setError("EkLink sign-in did not complete. Please try again.");
      return;
    }
    loginWithEklink(code, state)
      .then(() => navigate("/", { replace: true }))
      .catch((caught: unknown) => {
        setError(
          caught instanceof ApiError ? caught.message : "Unable to sign in with EkLink. Please try again.",
        );
      });
  }, [loginWithEklink, navigate, searchParams]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 p-6">
      <div className="w-full max-w-md rounded-2xl bg-white p-8 text-center shadow-sm">
        <p className="text-sm uppercase tracking-[0.2em] text-slate-500">TemplateOS</p>
        {error ? (
          <>
            <p className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>
            <Link className="mt-6 inline-block text-sm font-medium text-slate-900 underline" to="/login">
              Back to log in
            </Link>
          </>
        ) : (
          <p className="mt-4 text-sm text-slate-600">Signing you in with EkLink…</p>
        )}
      </div>
    </div>
  );
}
