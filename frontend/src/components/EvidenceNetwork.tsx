import { motion, useReducedMotion } from "framer-motion";

type NodeDef = { id: string; x: number; y: number; label: string; kind: "doc" | "entity" };

const NODES: NodeDef[] = [
  { id: "app", x: 120, y: 92, label: "APPLICATION.PDF", kind: "doc" },
  { id: "slip", x: 452, y: 70, label: "SALARY_SLIP.PNG", kind: "doc" },
  { id: "bank", x: 488, y: 300, label: "BANK_STATEMENT.PDF", kind: "doc" },
  { id: "id", x: 96, y: 318, label: "ID_PROOF.JPG", kind: "doc" },
  { id: "amount", x: 300, y: 128, label: "AMOUNT", kind: "entity" },
  { id: "entity", x: 230, y: 214, label: "ENTITY", kind: "entity" },
  { id: "date", x: 214, y: 352, label: "DATE", kind: "entity" },
  { id: "sig", x: 372, y: 226, label: "SIGNATURE", kind: "entity" },
];

const EDGES: { a: string; b: string; conflict?: boolean }[] = [
  { a: "app", b: "amount" },
  { a: "amount", b: "slip", conflict: true },
  { a: "app", b: "entity" },
  { a: "entity", b: "id" },
  { a: "id", b: "date" },
  { a: "date", b: "bank" },
  { a: "slip", b: "sig" },
  { a: "sig", b: "app" },
  { a: "sig", b: "bank" },
  { a: "entity", b: "slip" },
];

const byId = new Map(NODES.map((n) => [n.id, n]));

/** A quiet picture of what the product does: evidence across documents, being connected. Decorative only. */
export function EvidenceNetwork({ className }: { className?: string }) {
  const still = useReducedMotion();
  return (
    <svg viewBox="0 0 600 420" className={className} aria-hidden>
      <defs>
        <radialGradient id="net-fade" cx="50%" cy="50%" r="60%">
          <stop offset="0.55" stopColor="white" />
          <stop offset="1" stopColor="white" stopOpacity="0" />
        </radialGradient>
        <mask id="net-mask">
          <rect width="600" height="420" fill="url(#net-fade)" />
        </mask>
      </defs>
      <g mask="url(#net-mask)">
        {EDGES.map((e, i) => {
          const a = byId.get(e.a)!;
          const b = byId.get(e.b)!;
          return (
            <g key={i}>
              <line
                x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                stroke={e.conflict ? "var(--color-inc)" : "var(--color-accent)"}
                strokeOpacity={e.conflict ? 0.75 : 0.22}
                strokeWidth={e.conflict ? 1.4 : 1}
                strokeDasharray={e.conflict ? "6 5" : undefined}
                className={e.conflict && !still ? "net-march" : undefined}
              />
              {!still && (
                <motion.circle
                  r={e.conflict ? 2.6 : 1.8}
                  fill={e.conflict ? "var(--color-inc)" : "var(--color-accent)"}
                  initial={{ cx: a.x, cy: a.y, opacity: 0 }}
                  animate={{ cx: [a.x, b.x], cy: [a.y, b.y], opacity: [0, 1, 1, 0] }}
                  transition={{ duration: 3.2 + (i % 4) * 0.7, repeat: Infinity, delay: i * 0.55, ease: "easeInOut" }}
                />
              )}
            </g>
          );
        })}
        {NODES.map((n, i) => (
          <motion.g
            key={n.id}
            animate={still ? {} : { y: [0, i % 2 ? -4 : 4, 0] }}
            transition={{ duration: 6 + (i % 3), repeat: Infinity, ease: "easeInOut" }}
          >
            {n.kind === "doc" ? (
              <>
                <rect x={n.x - 15} y={n.y - 19} width="30" height="38" rx="4" fill="var(--color-panel)" stroke="var(--color-accent)" strokeOpacity="0.55" />
                <path d={`M${n.x - 8} ${n.y - 8} h16 M${n.x - 8} ${n.y - 1} h16 M${n.x - 8} ${n.y + 6} h10`} stroke="var(--color-accent)" strokeOpacity="0.45" strokeWidth="1.4" strokeLinecap="round" />
                <text x={n.x} y={n.y + 36} textAnchor="middle" className="fill-[var(--color-ink-3)] font-mono" fontSize="9.5" letterSpacing="1.4">
                  {n.label}
                </text>
              </>
            ) : (
              <>
                <circle cx={n.x} cy={n.y} r="13" fill="none" stroke={n.id === "amount" ? "var(--color-inc)" : "var(--color-accent)"} strokeOpacity="0.35" />
                <circle cx={n.x} cy={n.y} r="4.5" fill={n.id === "amount" ? "var(--color-inc)" : "var(--color-accent)"} />
                <text x={n.x} y={n.y + 28} textAnchor="middle" className="fill-[var(--color-ink-3)] font-mono" fontSize="9.5" letterSpacing="1.6">
                  {n.label}
                </text>
              </>
            )}
          </motion.g>
        ))}
      </g>
    </svg>
  );
}
