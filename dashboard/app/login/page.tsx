"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { Eye, EyeOff, Loader2 } from "lucide-react";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Keep post-login navigation on this site.
 *
 * Middleware only ever sets `next` to a pathname, but the query string is
 * whatever the visitor's URL says. Without this, a link to
 * `/login?next=https://example.com` would hand a freshly signed-in coach
 * straight to someone else's page. A protocol-relative `//host` is rejected
 * for the same reason.
 */
function safeNext(value: string | null): string {
  if (!value || !value.startsWith("/") || value.startsWith("//")) return "/";
  return value;
}

export default function LoginPage() {
  const router = useRouter();
  const nextPath = safeNext(useSearchParams().get("next"));

  const [academyId, setAcademyId] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [idError, setIdError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setFormError(null);
    setSubmitting(true);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ academyId, password }),
      });
      if (!res.ok) {
        const { error } = await res.json();
        setFormError(error ?? "Sign in failed.");
        return;
      }
      router.replace(nextPath);
      router.refresh();
    } catch {
      setFormError("Could not reach the dashboard server.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main id="main-content" className="mx-auto max-w-sm py-16">
      <div className="card">
        <h1 className="mb-1 text-base font-semibold text-slate-800">Sign in</h1>
        <p className="mb-5 text-sm text-slate-500">
          Use the academy ID and password for your club.
        </p>

        {formError && (
          <p
            role="alert"
            className="mb-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
          >
            {formError}
          </p>
        )}

        <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
          <div className="flex flex-col gap-2">
            <label
              htmlFor="academy-id"
              className="text-sm font-medium text-slate-700"
            >
              Academy ID
            </label>
            <input
              id="academy-id"
              name="username"
              autoComplete="username"
              required
              value={academyId}
              onChange={(e) => setAcademyId(e.target.value)}
              onBlur={() =>
                setIdError(
                  academyId && !UUID.test(academyId.trim())
                    ? "That does not look like an academy ID."
                    : null,
                )
              }
              aria-invalid={idError ? true : undefined}
              aria-describedby={
                idError ? "academy-id-error" : "academy-id-help"
              }
              className="rounded-md border border-slate-200 px-3 py-2 font-mono text-sm text-slate-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
            />
            {idError ? (
              <p
                id="academy-id-error"
                role="alert"
                className="text-xs text-red-600"
              >
                {idError}
              </p>
            ) : (
              <p id="academy-id-help" className="text-xs text-slate-400">
                A UUID, for example 18226b18-b9b6-4f1d-9cb8-1809d6b684fc
              </p>
            )}
          </div>

          <div className="flex flex-col gap-2">
            <label
              htmlFor="password"
              className="text-sm font-medium text-slate-700"
            >
              Password
            </label>
            <div className="relative">
              <input
                id="password"
                name="password"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-md border border-slate-200 px-3 py-2 pr-10 text-sm text-slate-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? "Hide password" : "Show password"}
                className="absolute inset-y-0 right-0 flex w-10 items-center justify-center text-slate-400 hover:text-slate-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
              >
                {showPassword ? (
                  <EyeOff className="h-4 w-4" aria-hidden="true" />
                ) : (
                  <Eye className="h-4 w-4" aria-hidden="true" />
                )}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={submitting || !academyId || !password}
            className="mt-1 inline-flex items-center justify-center gap-2 rounded-md bg-primary-800 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-primary-900 disabled:cursor-not-allowed disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
          >
            {submitting && (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            )}
            {submitting ? "Signing in" : "Sign in"}
          </button>
        </form>
      </div>
    </main>
  );
}
