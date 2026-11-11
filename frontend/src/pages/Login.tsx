import { LogIn } from "lucide-react";
import { useState, type FormEvent } from "react";

import { api } from "../api";
import { Button, ErrorBanner, Field, VillageCrest } from "../components/ui";

export default function Login({ onLoggedIn }: { onLoggedIn: () => Promise<void> | void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!username.trim() || !password) {
      setError("Enter your username and password.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.login(username.trim(), password);
      await onLoggedIn();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Login failed");
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-screen place-items-center p-6">
      <div className="w-full max-w-sm animate-rise">
        <div className="mb-8 flex flex-col items-center text-center">
          <VillageCrest size={52} />
          <h1 className="mt-5 text-2xl font-semibold tracking-tight text-mist-50">Welcome back, Chairman</h1>
          <p className="mt-1.5 text-sm text-mist-400">Sign in to enter your village.</p>
        </div>

        <form onSubmit={handleSubmit} noValidate className="panel space-y-3 p-6">
          {error && <ErrorBanner>{error}</ErrorBanner>}
          <Field id="login-username" label="Username">
            <input
              id="login-username"
              className="input"
              autoComplete="username"
              autoCapitalize="none"
              autoFocus
              value={username}
              onChange={(event) => setUsername(event.target.value)}
            />
          </Field>
          <Field id="login-password" label="Password">
            <input
              id="login-password"
              type="password"
              className="input"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </Field>
          <Button type="submit" busy={busy} icon={<LogIn size={16} aria-hidden="true" />} className="w-full">
            Log in
          </Button>
        </form>

        <p className="mt-6 text-center font-mono text-[11px] uppercase tracking-[0.14em] text-mist-500">
          Local only · 127.0.0.1
        </p>
      </div>
    </div>
  );
}
