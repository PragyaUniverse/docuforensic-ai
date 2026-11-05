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
  const field = "mt-1 h-10 w-full rounded-md border border-line-strong bg-panel px-3 text-ink";
  return (
    <div className="flex h-full items-center justify-center bg-ground p-6">
      <form
        className="w-full max-w-[360px] rounded-md border border-line bg-panel p-6"
        onSubmit={(e) => {
          e.preventDefault();
          login.mutate();
        }}
      >
        <h1 className="text-[20px] font-semibold">Sign in to DocuForensic</h1>
        <label className="mt-4 block text-[14px] text-ink-2">
          Username
          <input autoFocus autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} className={field} />
        </label>
        <label className="mt-3 block text-[14px] text-ink-2">
          Password
          <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} className={field} />
        </label>
        {login.isError && (
          <p role="alert" className="mt-3 text-[14px] text-man">
            {(login.error as Error).message}
          </p>
        )}
        <Button type="submit" variant="primary" className="mt-4 w-full" disabled={login.isPending || !username || !password}>
          Sign in
        </Button>
      </form>
    </div>
  );
}
