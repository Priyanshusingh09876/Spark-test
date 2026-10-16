/* Hand-rolled SVG bar chart. No library. */

interface Props {
  data: { label: string; value: number }[];
  height?: number;
  color?: string;
  valueSuffix?: string;
}

const PAD_TOP = 22;     // room for the value label above the tallest bar
const PAD_BOTTOM = 26;  // room for the category label under the baseline
const PAD_X = 12;
const SLOT_MIN = 72;

export default function BarChart({ data, height = 180, color = "var(--teal)", valueSuffix = "" }: Props) {
  const n = data.length;
  const width = Math.max(320, n * SLOT_MIN + PAD_X * 2);
  const slot = n ? (width - PAD_X * 2) / n : 0;
  const barW = Math.min(48, slot * 0.6);
  const plotH = height - PAD_TOP - PAD_BOTTOM;
  const max = Math.max(0, ...data.map((d) => d.value));
  const baseline = PAD_TOP + plotH;

  const summary = n
    ? data.map((d) => `${d.label} ${d.value}${valueSuffix}`).join(", ")
    : "no data";

  return (
    <div className="chart-wrap">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Bar chart: ${summary}`}>
        {data.map((d, i) => {
          const h = max > 0 ? (d.value / max) * plotH : 0;
          const x = PAD_X + slot * i + (slot - barW) / 2;
          const y = baseline - h;
          const cx = x + barW / 2;
          return (
            <g key={d.label}>
              <rect x={x} y={y} width={barW} height={h} rx={2} style={{ fill: color }} />
              <text
                x={cx} y={y - 6} textAnchor="middle"
                style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)", fill: "var(--ink)" }}
              >
                {d.value}{valueSuffix}
              </text>
              <text
                x={cx} y={baseline + 17} textAnchor="middle"
                style={{ fontFamily: "var(--font-sans)", fontSize: "var(--text-xs)", fill: "var(--muted)" }}
              >
                {d.label}
              </text>
            </g>
          );
        })}
        <line x1={PAD_X} x2={width - PAD_X} y1={baseline} y2={baseline} style={{ stroke: "var(--line)", strokeWidth: 1 }} />
        {n === 0 && (
          <text x={width / 2} y={height / 2} textAnchor="middle"
            style={{ fontSize: "var(--text-sm)", fill: "var(--muted-2)" }}>
            no data
          </text>
        )}
      </svg>
    </div>
  );
}
