import { useEffect, useId, useRef, useState } from "react";
import { motion, useMotionValue, useReducedMotion, useSpring } from "framer-motion";

export type Mood = "idle" | "hello" | "thinking" | "happy" | "concerned" | "oops";

const MOUTH: Record<Mood, string> = {
  idle: "M51 62 Q60 67 69 62",
  hello: "M48 60 Q60 73 72 60",
  happy: "M47 59 Q60 76 73 59",
  thinking: "M54 65 Q60 63 66 65",
  concerned: "M52 66 Q60 60 68 66",
  oops: "M53 67 Q60 58 67 67",
};

const GLOW: Record<Mood, string> = {
  idle: "#6fd6ff",
  hello: "#6fd6ff",
  happy: "#6ee7a8",
  thinking: "#ffd166",
  concerned: "#ffb347",
  oops: "#ff8a80",
};

const ORIGIN = { transformBox: "fill-box", transformOrigin: "center" } as const;

/** Doc: a small page-bodied helper with a magnifying glass. Drawn in-house, with no image assets. */
export function Mascot({ mood = "idle", size = 88, className }: { mood?: Mood; size?: number; className?: string }) {
  const id = useId().replace(/:/g, "");
  const still = useReducedMotion();
  const svg = useRef<SVGSVGElement>(null);
  const [blink, setBlink] = useState(false);
  const rawX = useMotionValue(0);
  const rawY = useMotionValue(0);
  const lookX = useSpring(rawX, { stiffness: 140, damping: 16 });
  const lookY = useSpring(rawY, { stiffness: 140, damping: 16 });

  // Eyes follow the pointer.
  useEffect(() => {
    if (still) return;
    const move = (e: PointerEvent) => {
      const r = svg.current?.getBoundingClientRect();
      if (!r) return;
      const dx = e.clientX - (r.left + r.width / 2);
      const dy = e.clientY - (r.top + r.height * 0.33);
      const distance = Math.hypot(dx, dy) || 1;
      const reach = Math.min(distance / 60, 1);
      rawX.set((dx / distance) * 3.4 * reach);
      rawY.set((dy / distance) * 2.6 * reach);
    };
    window.addEventListener("pointermove", move, { passive: true });
    return () => window.removeEventListener("pointermove", move);
  }, [still, rawX, rawY]);

  // Blinks at uneven, human-feeling intervals.
  useEffect(() => {
    if (still) return;
    let timer: number;
    const schedule = () => {
      timer = window.setTimeout(() => {
        setBlink(true);
        window.setTimeout(() => setBlink(false), 130);
        schedule();
      }, 1800 + Math.random() * 3600);
    };
    schedule();
    return () => window.clearTimeout(timer);
  }, [still]);

  const glow = GLOW[mood];
  const bounce = mood === "happy" || mood === "hello";
  const bob = still
    ? {}
    : bounce
      ? { y: [0, -9, 0, -5, 0] }
      : mood === "thinking"
        ? { y: [0, -3, 0] }
        : { y: [0, -5, 0] };
  const bobTime = bounce ? { duration: 1.2, repeat: Infinity, repeatDelay: 1.6, ease: "easeInOut" as const } : { duration: mood === "thinking" ? 1.4 : 3, repeat: Infinity, ease: "easeInOut" as const };
  const lean = mood === "concerned" ? -5 : mood === "oops" ? 5 : 0;
  const eyeScale = blink ? 0.08 : mood === "happy" || mood === "hello" ? 0.78 : mood === "thinking" ? 0.86 : 1;
  const browOn = mood === "concerned" || mood === "oops" || mood === "thinking";

  return (
    <svg ref={svg} viewBox="0 0 120 142" width={size} height={size * (142 / 120)} className={className} aria-hidden style={{ overflow: "visible" }}>
      <defs>
        <linearGradient id={`${id}h`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#6aa8ec" />
          <stop offset="1" stopColor="#2a68b0" />
        </linearGradient>
        <linearGradient id={`${id}s`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#16283f" />
          <stop offset="1" stopColor="#0d1a2c" />
        </linearGradient>
        <linearGradient id={`${id}b`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#ffffff" />
          <stop offset="1" stopColor="#e6ecf4" />
        </linearGradient>
        <radialGradient id={`${id}g`}>
          <stop offset="0" stopColor={glow} stopOpacity="0.9" />
          <stop offset="1" stopColor={glow} stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* Shadow shrinks as Doc rises. */}
      <motion.ellipse
        cx="60" cy="136" rx="30" ry="4.5" fill="#000" opacity="0.14" style={ORIGIN}
        animate={still ? {} : { scaleX: [1, 0.84, 1] }}
        transition={{ duration: bounce ? 1.2 : 3, repeat: Infinity, repeatDelay: bounce ? 1.6 : 0, ease: "easeInOut" }}
      />

      <motion.g animate={bob} transition={bobTime}>
        <motion.g animate={{ rotate: lean }} transition={{ type: "spring", stiffness: 120, damping: 12 }} style={{ transformBox: "fill-box", transformOrigin: "50% 100%" }}>
          {/* Waving arm */}
          <motion.g
            style={{ transformBox: "fill-box", transformOrigin: "100% 100%" }}
            animate={still ? {} : mood === "hello" || mood === "happy" ? { rotate: [0, 24, -6, 24, 0] } : { rotate: 0 }}
            transition={{ duration: 1.1, repeat: mood === "hello" || mood === "happy" ? Infinity : 0, repeatDelay: 1.7 }}
          >
            <path d="M31 96 Q16 92 13 76" fill="none" stroke="#2a68b0" strokeWidth="6" strokeLinecap="round" />
            <circle cx="13" cy="73" r="5.5" fill="#6aa8ec" />
          </motion.g>

          {/* Page body */}
          <path d="M34 82 H78 L90 94 V126 Q90 132 84 132 H40 Q34 132 34 126 Z" fill={`url(#${id}b)`} stroke="#b9c8da" strokeWidth="1.5" />
          <path d="M78 82 V94 H90 Z" fill="#cfdbe9" />
          <motion.g animate={still || mood !== "thinking" ? { opacity: 1 } : { opacity: [1, 0.45, 1] }} transition={{ duration: 1.4, repeat: Infinity }}>
            <rect x="42" y="100" width="28" height="3.5" rx="1.75" fill="#9fb3ca" />
            <rect x="42" y="109" width="40" height="3.5" rx="1.75" fill="#b6c6d8" />
            <rect x="42" y="118" width="33" height="3.5" rx="1.75" fill="#b6c6d8" />
          </motion.g>

          {/* Magnifying glass: sweeps across the page while checking. */}
          <motion.g
            animate={still ? {} : mood === "thinking" ? { x: [-30, 0, -30], y: [-4, 6, -4] } : { x: 0, y: 0 }}
            transition={mood === "thinking" ? { duration: 2.2, repeat: Infinity, ease: "easeInOut" } : { duration: 0.4 }}
          >
            <path d="M89 112 Q100 108 101 99" fill="none" stroke="#2a68b0" strokeWidth="6" strokeLinecap="round" />
            <line x1="100" y1="100" x2="94" y2="92" stroke="#415a78" strokeWidth="4.5" strokeLinecap="round" />
            <circle cx="88" cy="83" r="11" fill="#dff1ff" fillOpacity="0.55" stroke="#415a78" strokeWidth="4" />
            <path d="M82 79 Q84 75 88 75" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" />
          </motion.g>

          {/* Head: sways gently, and tilts when something needs a closer look. */}
          <motion.g
            style={{ transformBox: "fill-box", transformOrigin: "50% 100%" }}
            animate={still ? {} : mood === "thinking" ? { rotate: [-3, 3, -3] } : { rotate: [-1.5, 1.5, -1.5] }}
            transition={{ duration: mood === "thinking" ? 2.2 : 5, repeat: Infinity, ease: "easeInOut" }}
          >
            {/* Antenna */}
            <line x1="60" y1="27" x2="60" y2="13" stroke="#2a68b0" strokeWidth="4" strokeLinecap="round" />
            <motion.circle cx="60" cy="9" r="12" fill={`url(#${id}g)`} style={ORIGIN} animate={still ? {} : { scale: [0.75, 1.15, 0.75] }} transition={{ duration: mood === "thinking" ? 0.9 : 2.4, repeat: Infinity, ease: "easeInOut" }} />
            <motion.circle cx="60" cy="9" r="5" animate={{ fill: glow }} transition={{ duration: 0.4 }} />

            <rect x="24" y="26" width="72" height="58" rx="20" fill={`url(#${id}h)`} />
            <rect x="17" y="46" width="9" height="18" rx="4.5" fill="#2a68b0" />
            <rect x="94" y="46" width="9" height="18" rx="4.5" fill="#2a68b0" />
            <rect x="32" y="34" width="56" height="42" rx="14" fill={`url(#${id}s)`} />
            <path d="M38 40 Q50 36 60 37" fill="none" stroke="#fff" strokeOpacity="0.18" strokeWidth="2.5" strokeLinecap="round" />

            {/* Eyes */}
            <motion.g style={{ x: lookX, y: lookY }}>
              {[47, 73].map((cx) => (
                <motion.ellipse
                  key={cx} cx={cx} cy="52" rx="6" ry="7.5" style={ORIGIN}
                  animate={{ scaleY: eyeScale, fill: glow }}
                  transition={{ scaleY: { duration: 0.08 }, fill: { duration: 0.4 } }}
                />
              ))}
              {!blink && <circle cx="45" cy="49" r="1.8" fill="#fff" opacity="0.9" />}
              {!blink && <circle cx="71" cy="49" r="1.8" fill="#fff" opacity="0.9" />}
            </motion.g>

            {/* Brows */}
            <motion.g animate={{ opacity: browOn ? 1 : 0 }} transition={{ duration: 0.2 }}>
              <motion.line x1="41" x2="52" stroke={glow} strokeWidth="2.6" strokeLinecap="round"
                animate={mood === "thinking" ? { y1: 41, y2: 39 } : { y1: 40, y2: 44 }} />
              <motion.line x1="68" x2="79" stroke={glow} strokeWidth="2.6" strokeLinecap="round"
                animate={mood === "thinking" ? { y1: 43, y2: 43 } : { y1: 44, y2: 40 }} />
            </motion.g>

            {/* Cheeks */}
            <motion.g animate={{ opacity: mood === "happy" || mood === "hello" ? 0.55 : 0 }}>
              <ellipse cx="38" cy="63" rx="4.5" ry="2.5" fill="#ff9db0" />
              <ellipse cx="82" cy="63" rx="4.5" ry="2.5" fill="#ff9db0" />
            </motion.g>

            <motion.path fill="none" strokeLinecap="round" strokeWidth="3" stroke={glow} initial={false} animate={{ d: MOUTH[mood] }} transition={{ duration: 0.25 }} />
          </motion.g>
        </motion.g>
      </motion.g>

      {/* Dots orbit while checking. */}
      {mood === "thinking" && !still && [0, 0.35, 0.7].map((delay) => (
        <motion.circle key={delay} cx="104" cy="22" r="2.6" fill={glow} animate={{ y: [0, -8, 0], opacity: [0.25, 1, 0.25] }} transition={{ duration: 1.05, repeat: Infinity, delay }} style={{ translateX: delay * 16 - 6 }} />
      ))}
    </svg>
  );
}
