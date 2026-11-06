import { motion, useReducedMotion } from "framer-motion";
import { cn } from "@/lib/utils";

export type OrbState = "idle" | "thinking" | "alert" | "done";

const TONE: Record<OrbState, string> = {
  idle: "var(--color-accent)",
  thinking: "var(--color-accent)",
  alert: "var(--color-inc)",
  done: "var(--color-ok)",
};

/** Doc's presence: a small lit core with orbiting rings. It speeds up while working. */
export function DocOrb({ state = "idle", size = 40, className }: { state?: OrbState; size?: number; className?: string }) {
  const still = useReducedMotion();
  const tone = TONE[state];
  const fast = state === "thinking";
  return (
    <span className={cn("relative inline-flex shrink-0 items-center justify-center", className)} style={{ width: size, height: size }} aria-hidden>
      <span className="absolute inset-0 rounded-full blur-md" style={{ background: tone, opacity: 0.28 }} />
      <svg viewBox="0 0 40 40" width={size} height={size} className="relative">
        <motion.circle
          cx="20" cy="20" r="17" fill="none" stroke={tone} strokeOpacity="0.35" strokeWidth="1" strokeDasharray="3 5"
          style={{ transformOrigin: "20px 20px" }}
          animate={still ? {} : { rotate: 360 }}
          transition={{ duration: fast ? 3 : 14, repeat: Infinity, ease: "linear" }}
        />
        <motion.circle
          cx="20" cy="20" r="12" fill="none" stroke={tone} strokeOpacity="0.6" strokeWidth="1.2" strokeDasharray="18 58"
          style={{ transformOrigin: "20px 20px" }}
          animate={still ? {} : { rotate: -360 }}
          transition={{ duration: fast ? 1.6 : 7, repeat: Infinity, ease: "linear" }}
        />
        <motion.circle
          cx="20" cy="20" r="5.5" fill={tone}
          style={{ transformOrigin: "20px 20px" }}
          animate={still ? {} : { scale: fast ? [0.85, 1.15, 0.85] : [0.95, 1.05, 0.95], opacity: [0.85, 1, 0.85] }}
          transition={{ duration: fast ? 0.9 : 2.8, repeat: Infinity, ease: "easeInOut" }}
        />
        <circle cx="18.2" cy="18.2" r="1.6" fill="white" opacity="0.7" />
      </svg>
    </span>
  );
}
