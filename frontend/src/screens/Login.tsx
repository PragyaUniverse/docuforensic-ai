import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { accountApi } from "@/api/account";
import { Button } from "@/components/ui/button";

export function LoginScreen() {
  const qc = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const login = useMutation({
    mutationFn: () => accountApi.login(username, password),
    onSuccess: () => {
      setPassword("");
      qc.invalidateQueries();
    },
  });
  const field =
    "mt-1.5 h-10 w-full rounded-md border border-line-strong bg-ground/60 px-3 font-mono text-[14px] text-ink outline-none transition-[border-color,box-shadow] focus:border-accent focus:shadow-[0_0_0_3px_rgba(var(--color-glow),0.15)]";
  return (
    <div className="flex h-full flex-col items-center justify-center gap-6 p-6">
      <div className="flex items-center gap-2.5" aria-hidden>
        <svg viewBox="0 0 24 24" className="size-7 text-accent">
          <circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.5" />
          <circle cx="12" cy="12" r="4" fill="currentColor" />
        </svg>
        <span className="font-mono text-[15px] font-semibold tracking-[0.28em] text-ink">DOCUFORENSIC</span>
      </div>
      <form
        className="panel scanline glow-cyan w-full max-w-[380px] p-7"
        onSubmit={(e) => {
          e.preventDefault();
          login.mutate();
        }}
      >
        <div className="mono-label flex items-center gap-2 text-accent">
          <span className="status-dot" /> Secure access
        </div>
        <h1 className="mt-2 text-[22px] font-semibold tracking-tight">Sign in to continue</h1>
        <p className="mt-1 text-[13.5px] text-ink-3">Every action you take is written to the investigation timeline.</p>
        <label className="mono-label mt-6 block !text-ink-2">
          Username
          <input autoFocus autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} className={field} />
        </label>
        <label className="mono-label mt-4 block !text-ink-2">
          Password
          <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} className={field} />
        </label>
        {login.isError && (
          <p role="alert" className="mt-3 text-[14px] text-man">
            {(login.error as Error).message}
          </p>
        )}
        <Button type="submit" variant="primary" className="mt-6 w-full" size="lg" disabled={login.isPending || !username || !password}>
          Sign in
        </Button>
      </form>
    </div>
  );
}
