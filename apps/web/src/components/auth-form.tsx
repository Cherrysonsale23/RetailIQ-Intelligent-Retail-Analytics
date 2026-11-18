
"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useState } from "react";
import { createClient } from "@/lib/supabase/client";

type Mode = "sign-in" | "sign-up" | "forgot-password";

const copy = {
  "sign-in": {
    title: "Welcome back",
    subtitle: "Sign in to continue to your analytics workspace.",
    action: "Sign in",
    busy: "Signing in...",
  },
  "sign-up": {
    title: "Create your workspace",
    subtitle: "Start exploring your business data with confidence.",
    action: "Create account",
    busy: "Creating account...",
  },
  "forgot-password": {
    title: "Reset your password",
    subtitle: "We'll email you a secure link to choose a new password.",
    action: "Send reset link",
    busy: "Sending...",
  },
} as const;

export function AuthForm({ mode }: { mode: Mode }) {
  const router = useRouter();
  const params = useSearchParams();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const config = copy[mode];

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setMessage("");
    setBusy(true);

    try {
      const supabase = createClient();

      if (mode === "sign-in") {
        const { error: authError } =
          await supabase.auth.signInWithPassword({
            email,
            password,
          });

        if (authError) throw authError;

        router.replace(params.get("next") || "/overview");
        router.refresh();
      } else if (mode === "sign-up") {
        const { data, error: authError } =
          await supabase.auth.signUp({
            email,
            password,
            options: {
              emailRedirectTo: `${window.location.origin}/auth/callback?next=/overview`,
            },
          });

        if (authError) throw authError;

        if (data.session) {
          router.replace("/overview");
          router.refresh();
        } else {
          setMessage(
            "Account registration received. Check your email to confirm your account, then sign in."
          );
        }
      } else {
        const { error: authError } =
          await supabase.auth.resetPasswordForEmail(email, {
            redirectTo: `${window.location.origin}/auth/callback?next=/auth/update-password`,
          });

        if (authError) throw authError;

        setMessage(
          "If an account exists for that email, a password reset link is on its way."
        );
      }
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Something went wrong. Please try again."
      );
    } finally {
      setBusy(false);
    }
  }

  async function google() {
    setBusy(true);
    setError("");

    try {
      const supabase = createClient();

      const { error: authError } =
        await supabase.auth.signInWithOAuth({
          provider: "google",
          options: {
            redirectTo: `${window.location.origin}/auth/callback?next=/overview`,
          },
        });

      if (authError) throw authError;
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Google sign in could not start."
      );
      setBusy(false);
    }
  }

  return (
    <div className="auth-shell">
      <section className="auth-form-wrap">
        <div className="auth-form">
          <Link href="/" className="brand">
            <span className="brand-mark">M</span>
            <span>
              Meridian<span style={{ color: "#146b54" }}>.</span>
            </span>
          </Link>

          <h1 className="auth-title">{config.title}</h1>
          <p className="auth-subtitle">{config.subtitle}</p>

          {mode !== "forgot-password" && (
            <>
              <button
                className="secondary-btn"
                type="button"
                onClick={google}
                disabled={busy}
              >
                <GoogleMark /> Continue with Google
              </button>
              <div className="auth-divider">or continue with email</div>
            </>
          )}

          <form onSubmit={submit}>
            <div className="field">
              <label htmlFor="email">Email address</label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
              />
            </div>

            {mode !== "forgot-password" && (
              <div className="field">
                <label htmlFor="password">Password</label>
                <input
                  id="password"
                  type="password"
                  autoComplete={
                    mode === "sign-up" ? "new-password" : "current-password"
                  }
                  minLength={8}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="At least 8 characters"
                />
              </div>
            )}

            {mode === "sign-in" && (
              <div className="inline-row">
                <span>Secure access to your data</span>
                <Link className="text-link" href="/forgot-password">
                  Forgot password?
                </Link>
              </div>
            )}

            {error && (
              <p
                role="alert"
                style={{ color: "#b42318", fontSize: 13, margin: "12px 0" }}
              >
                {error}
              </p>
            )}

            {message && (
              <p
                role="status"
                style={{ color: "#146b54", fontSize: 13, margin: "12px 0" }}
              >
                {message}
              </p>
            )}

            <button className="primary-btn" disabled={busy}>
              {busy ? config.busy : config.action}
            </button>
          </form>

          <p className="auth-foot">
            {mode === "sign-in" ? (
              <>
                New to Meridian?{" "}
                <Link className="text-link" href="/sign-up">
                  Create an account
                </Link>
              </>
            ) : mode === "sign-up" ? (
              <>
                Already have an account?{" "}
                <Link className="text-link" href="/sign-in">
                  Sign in
                </Link>
              </>
            ) : (
              <>
                Remembered it?{" "}
                <Link className="text-link" href="/sign-in">
                  Back to sign in
                </Link>
              </>
            )}
          </p>
        </div>
      </section>

      <aside className="auth-art">
        <div className="brand" style={{ color: "white" }}>
          <span
            className="brand-mark"
            style={{ background: "#ffffff20", color: "white" }}
          >
            M
          </span>
          Meridian Analytics
        </div>

        <div>
          <div className="art-eyebrow">Decision intelligence</div>
          <h2 className="art-title">
            Every answer,
            <br />
            grounded in data.
          </h2>
          <p className="art-copy">
            Explore customer behavior, understand product performance, and
            turn real business data into clear next steps.
          </p>
        </div>

        <div className="art-card">
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              fontSize: 12,
              color: "#e2f4ea",
            }}
          >
            <span>Private by design</span>
            <span>✦</span>
          </div>

          <div className="privacy-orbit">
            <i />
            <i />
            <i />
            <b />
          </div>

          <div
            style={{ fontSize: 11, color: "#c8e6d6", marginTop: 12 }}
          >
            Your workspace stays empty until you add your own data.
          </div>
        </div>
      </aside>
    </div>
  );
}

function GoogleMark() {
  return (
    <svg
      width="17"
      height="17"
      viewBox="0 0 48 48"
      aria-hidden="true"
    >
      <path
        fill="#FFC107"
        d="M43.6 24.5c0-1.4-.1-2.8-.4-4.1H24v7.8h11a9.4 9.4 0 0 1-4.1 6.2v5.1h6.7c3.9-3.6 6-8.8 6-15Z"
      />
      <path
        fill="#34A853"
        d="M24 44c5.6 0 10.3-1.9 13.7-5.1L31 33.8c-1.9 1.3-4.2 2.1-7 2.1-5.4 0-10-3.7-11.7-8.7H5.4v5.3A20 20 0 0 0 24 44Z"
      />
      <path
        fill="#4A90E2"
        d="M12.3 27.2a12 12 0 0 1 0-6.4v-5.3H5.4a20 20 0 0 0 0 17Z"
      />
      <path
        fill="#EA4335"
        d="M24 12.1c3 0 5.7 1 7.8 3.1l5.8-5.8C34.3 6 29.6 4 24 4A20 20 0 0 0 5.4 15.5l6.9 5.3c1.7-5 6.3-8.7 11.7-8.7Z"
      />
    </svg>
  );
}