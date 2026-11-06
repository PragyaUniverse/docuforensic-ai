import { useEffect, useState } from "react";
import { animate, motion, useReducedMotion } from "framer-motion";

/** Counts up from zero when it first appears. */
export function CountUp({ value, className }: { value: number; className?: string }) {
  const still = useReducedMotion();
  const [shown, setShown] = useState(still ? value : 0);
  useEffect(() => {
    if (still) {
      setShown(value);
      return;
    }
    const controls = animate(0, value, { duration: 0.9, ease: "easeOut", onUpdate: (v) => setShown(Math.round(v)) });
    return () => controls.stop();
  }, [value, still]);
  return <span className={className}>{shown}</span>;
}

/** A thin ring that fills to `fraction`, with a soft glow. */
export function Ring({ fraction, size = 132, tone = "var(--color-accent)", children }: { fraction: number; size?: number; tone?: string; children?: React.ReactNode }) {
  const still = useReducedMotion();
  const r = 52;
  const length = 2 * Math.PI * r;
  const clamped = Math.max(0, Math.min(1, fraction));
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg viewBox="0 0 120 120" width={size} height={size} className="-rotate-90">
        <circle cx="60" cy="60" r={r} fill="none" stroke="var(--color-line)" strokeWidth="6" />
        <circle cx="60" cy="60" r={r} fill="none" stroke="var(--color-line-strong)" strokeWidth="1" strokeDasharray="1 5" opacity="0.6" transform="scale(0.86) translate(9.8 9.8)" />
        <motion.circle
          cx="60" cy="60" r={r} fill="none" stroke={tone} strokeWidth="6" strokeLinecap="round"
          strokeDasharray={length}
          initial={{ strokeDashoffset: length }}
          animate={{ strokeDashoffset: length * (1 - clamped) }}
          transition={still ? { duration: 0 } : { duration: 1.1, ease: "easeOut" }}
          style={{ filter: `drop-shadow(0 0 6px ${tone})` }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">{children}</div>
    </div>
  );
}

/** An animated confidence bar. */
export function ConfidenceBar({ value, tone = "bg-accent" }: { value: number; tone?: string }) {
  const still = useReducedMotion();
  return (
    <div className="h-1.5 overflow-hidden rounded-full bg-line" aria-hidden>
      <motion.div
        className={`h-full rounded-full ${tone}`}
        initial={{ width: 0 }}
        animate={{ width: `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%` }}
        transition={still ? { duration: 0 } : { duration: 0.9, ease: "easeOut", delay: 0.15 }}
      />
    </div>
  );
}
