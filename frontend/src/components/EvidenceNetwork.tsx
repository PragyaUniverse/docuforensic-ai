import { motion, useReducedMotion } from "framer-motion";

type NodeDef = { id: string; x: number; y: number; label: string; kind: "doc" | "entity" };

const NODES: NodeDef[] = [
  { id: "app", x: 124, y: 92, label: "APPLICATION.PDF", kind: "doc" },
  { id: "slip", x: 452, y: 70, label: "SALARY_SLIP.PNG", kind: "doc" },
  { id: "bank", x: 470, y: 300, label: "BANK_STATEMENT.PDF", kind: "doc" },
  { id: "id", x: 110, y: 318, label: "ID_PROOF.JPG", kind: "doc" },
  { id: "amount", x: 300, y: 128, label: "AMOUNT", kind: "entity" },
  { id: "entity", x: 230, y: 214, label: "ENTITY", kind: "entity" },
  { id: "date", x: 222, y: 352, label: "DATE", kind: "entity" },
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
  // Labels sit on a halo of the page colour, so they stay readable where lines cross them.
  const label = "fill-[var(--color-ink-2)] font-mono font-semibold [paint-order:stroke] [stroke:var(--color-ground)] [stroke-width:4px] [stroke-linejoin:round]";
  return (
    <svg viewBox="0 0 600 420" className={className} aria-hidden overflow="visible">
      <defs>
        <filter id="net-glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="3" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      <g>
        {EDGES.map((e, i) => {
          const a = byId.get(e.a)!;
          const b = byId.get(e.b)!;
          return (
            <g key={i}>
              <line
                x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                stroke={e.conflict ? "var(--color-inc)" : "var(--color-accent)"}
                strokeOpacity={e.conflict ? 1 : 0.55}
                strokeWidth={e.conflict ? 2.2 : 1.5}
                strokeDasharray={e.conflict ? "7 5" : undefined}
                filter={e.conflict ? "url(#net-glow)" : undefined}
                className={e.conflict && !still ? "net-march" : undefined}
              />
              {!still && (
                <motion.circle
                  r={e.conflict ? 3.4 : 2.6}
                  fill={e.conflict ? "var(--color-inc)" : "var(--color-accent)"}
                  filter="url(#net-glow)"
                  initial={{ cx: a.x, cy: a.y, opacity: 0 }}
                  animate={{ cx: [a.x, b.x], cy: [a.y, b.y], opacity: [0, 1, 1, 0] }}
                  transition={{ duration: 3.2 + (i % 4) * 0.7, repeat: Infinity, delay: i * 0.55, ease: "easeInOut" }}
                />
              )}
            </g>
          );
        })}
        {NODES.map((n, i) => {
          const tone = n.id === "amount" ? "var(--color-inc)" : "var(--color-accent)";
          return (
            <motion.g
              key={n.id}
              animate={still ? {} : { y: [0, i % 2 ? -4 : 4, 0] }}
              transition={{ duration: 6 + (i % 3), repeat: Infinity, ease: "easeInOut" }}
            >
              {n.kind === "doc" ? (
                <>
                  <rect x={n.x - 17} y={n.y - 21} width="34" height="42" rx="5" fill="var(--color-panel)" stroke="var(--color-accent)" strokeWidth="1.6" />
                  <path d={`M${n.x - 9} ${n.y - 9} h18 M${n.x - 9} ${n.y - 1} h18 M${n.x - 9} ${n.y + 7} h11`} stroke="var(--color-accent)" strokeWidth="1.8" strokeLinecap="round" />
                  <text x={n.x} y={n.y + 40} textAnchor="middle" className={label} fontSize="11" letterSpacing="1.2">
                    {n.label}
                  </text>
                </>
              ) : (
                <>
                  <circle cx={n.x} cy={n.y} r="14" fill="var(--color-panel)" stroke={tone} strokeWidth="1.6" strokeOpacity="0.85" />
                  <circle cx={n.x} cy={n.y} r="6" fill={tone} filter="url(#net-glow)" />
                  <text x={n.x} y={n.y + 31} textAnchor="middle" className={label} fontSize="11" letterSpacing="1.5">
                    {n.label}
                  </text>
                </>
              )}
            </motion.g>
          );
        })}
      </g>
    </svg>
  );
}
