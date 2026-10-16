/* Hand-rolled SVG donut using stroke-dasharray on stacked circles. */

interface Slice { label: string; value: number; color: string }

interface Props {
  slices: Slice[];
  size?: number;
  centerLabel?: string;
}

const STROKE = 18;

export default function DonutChart({ slices, size = 160, centerLabel }: Props) {
  const r = (size - STROKE) / 2;
  const c = 2 * Math.PI * r;
  const total = slices.reduce((s, x) => s + x.value, 0);
  const cx = size / 2;
  const cy = size / 2;

  const summary = total
    ? slices.map((s) => `${s.label} ${s.value}`).join(", ")
    : "no data";

  let offset = 0;
  return (
    <div className="donut">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`Donut chart: ${summary}`}>
        {total === 0 ? (
          <circle cx={cx} cy={cy} r={r} fill="none" strokeWidth={STROKE} style={{ stroke: "var(--line)" }} />
        ) : (
          slices.filter((s) => s.value > 0).map((s) => {
            const len = (s.value / total) * c;
            const el = (
              <circle
                key={s.label}
                cx={cx} cy={cy} r={r}
                fill="none"
                strokeWidth={STROKE}
                strokeDasharray={`${len} ${c - len}`}
                strokeDashoffset={-offset}
                transform={`rotate(-90 ${cx} ${cy})`}
                style={{ stroke: s.color }}
              />
            );
            offset += len;
            return el;
          })
        )}
        <text
          x={cx} y={cy + 1} textAnchor="middle" dominantBaseline="middle"
          style={{
            fontFamily: "var(--font-mono)", fontWeight: 500,
            fontSize: total === 0 ? "var(--text-sm)" : "var(--text-xl)",
            fill: total === 0 ? "var(--muted-2)" : "var(--ink)",
          }}
        >
          {total === 0 ? "no data" : (centerLabel ?? String(total))}
        </text>
      </svg>
      <div className="legend">
        {slices.map((s) => (
          <div className="legend-item" key={s.label}>
            <span className="legend-swatch" style={{ background: s.color }} />
            <span>{s.label}</span>
            <span className="legend-value">{s.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
