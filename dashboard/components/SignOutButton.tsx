"use client";

import { useRouter } from "next/navigation";

export default function SignOutButton() {
  const router = useRouter();
  return (
    <button
      type="button"
      onClick={async () => {
        await fetch("/api/auth/logout", { method: "POST" });
        router.replace("/login");
        router.refresh();
      }}
      className="rounded px-1 text-xs font-medium text-slate-400 transition-colors duration-150 hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400"
    >
      Sign out
    </button>
  );
}
