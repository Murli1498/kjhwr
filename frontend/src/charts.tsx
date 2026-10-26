import {
  Area,
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { AccuracyPayload, HourRow } from "./types";

export const ink = "#1c1814";
export const muted = "#5c564c";
export const wind = "#0d6a4c";
export const windSoft = "#c5ddd2";
export const short = "#8d3416";
export const long = "#1a4e7a";
export const grid = "#e4d8c4";

type TipRow = { name?: string; value?: number | string; color?: string; dataKey?: string | number };
type TipProps = { active?: boolean; label?: string | number; payload?: TipRow[] };

function Tip({ active, payload, label }: TipProps) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="tip">
      {label != null && label !== "" ? <strong>{label}</strong> : null}
      {payload
        .filter((row) => {
          const key = String(row.dataKey ?? "");
          return row.value != null && row.name != null && !["bandBase", "bandWidth", "guide"].includes(key);
        })
        .map((row) => (
          <div key={String(row.dataKey)}>
            <i style={{ background: row.color }} />
            <span>{row.name}</span>
            <b>{typeof row.value === "number" ? row.value.toLocaleString("en-GB") : row.value}</b>
          </div>
        ))}
    </div>
  );
}

const axis = { fill: muted, fontSize: 12, fontFamily: "IBM Plex Sans, sans-serif" };

export function ProfileChart({ hours, showOutturn }: { hours: HourRow[]; showOutturn: boolean }) {
  const points = hours.flatMap((hour) => {
    const low = hour.band_low_mw;
    const high = hour.band_high_mw;
    const base = low == null || high == null ? null : Math.min(low, high);
    const width = low == null || high == null || base == null ? null : Math.abs(high - low);
    const half = (suffix: string, actual: number | null) => ({
      label: `${hour.label.slice(0, 2)}:${suffix}`,
      forecast: hour.forecast_mw,
      actual: showOutturn ? actual : null,
      bandBase: base,
      bandWidth: width,
    });
    return [half("00", hour.actual_sp1_mw), half("30", hour.actual_sp2_mw)];
  });
  const ticks = points.filter((_, index) => index % 4 === 0).map((point) => point.label);
  const hasBand = points.some((point) => point.bandWidth != null);
  const highs = points.map((point) =>
    Math.max(point.forecast, point.actual ?? 0, (point.bandBase ?? 0) + (point.bandWidth ?? 0)),
  );
  const peak = highs.length === 0 ? 1000 : Math.max(...highs);
  const top = Math.max(1000, Math.ceil((peak * 1.08) / 1000) * 1000);

  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={points} margin={{ top: 12, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid stroke={grid} vertical={false} />
        <XAxis dataKey="label" ticks={ticks} tick={axis} tickLine={false} axisLine={false} interval={0} />
        <YAxis
          tick={axis}
          tickLine={false}
          axisLine={false}
          width={56}
          domain={[0, top]}
          tickFormatter={(value: number) => `${Math.round(value / 1000)}k`}
        />
        <Tooltip content={<Tip />} />
        {hasBand ? (
          <Area dataKey="bandBase" stackId="band" stroke="none" fill="transparent" name="bandBase" activeDot={false} />
        ) : null}
        {hasBand ? (
          <Area dataKey="bandWidth" stackId="band" stroke="none" fill={windSoft} name="Error band" isAnimationActive={false} />
        ) : null}
        <Line
          type="stepAfter"
          dataKey="forecast"
          name="Forecast"
          stroke={wind}
          strokeWidth={2.2}
          dot={false}
          isAnimationActive={false}
        />
        {showOutturn ? (
          <Line
            type="monotone"
            dataKey="actual"
            name="Outturn"
            stroke={ink}
            strokeWidth={1.6}
            dot={false}
            connectNulls
            isAnimationActive={false}
          />
        ) : null}
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export function DailyErrorChart({ days }: { days: AccuracyPayload["by_day"] }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={days} margin={{ top: 12, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid stroke={grid} vertical={false} />
        <XAxis dataKey="label" tick={axis} tickLine={false} axisLine={false} interval={2} />
        <YAxis tick={axis} tickLine={false} axisLine={false} width={48} tickFormatter={(value: number) => `${Math.round(value / 1000)}k`} />
        <ReferenceLine y={0} stroke={ink} strokeOpacity={0.45} />
        <Tooltip content={<Tip />} />
        <Bar dataKey="error_mwh" name="Energy error MWh" isAnimationActive={false}>
          {days.map((day) => (
            <Cell key={day.delivery} fill={day.error_mwh >= 0 ? short : long} />
          ))}
        </Bar>
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export function HourBiasChart({ hours }: { hours: AccuracyPayload["by_hour"] }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={hours} margin={{ top: 12, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid stroke={grid} vertical={false} />
        <XAxis dataKey="label" tick={axis} tickLine={false} axisLine={false} interval={1} />
        <YAxis tick={axis} tickLine={false} axisLine={false} width={48} />
        <ReferenceLine y={0} stroke={ink} strokeOpacity={0.45} />
        <Tooltip content={<Tip />} />
        <Bar dataKey="bias_mw" name="Bias MW" isAnimationActive={false}>
          {hours.map((hour) => (
            <Cell key={hour.label} fill={hour.bias_mw >= 0 ? short : long} />
          ))}
        </Bar>
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export function VintageChart({ rows }: { rows: AccuracyPayload["by_vintage"] }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={rows} margin={{ top: 12, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid stroke={grid} vertical={false} />
        <XAxis dataKey="slot_local" tick={axis} tickLine={false} axisLine={false} />
        <YAxis tick={axis} tickLine={false} axisLine={false} width={48} />
        <Tooltip content={<Tip />} />
        <Bar dataKey="mae_mw" name="MAE MW" isAnimationActive={false}>
          {rows.map((row) => (
            <Cell key={row.slot_local} fill={wind} fillOpacity={row.before_gate ? 1 : 0.35} />
          ))}
        </Bar>
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export function HistogramChart({ bins }: { bins: AccuracyPayload["histogram"] }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={bins} margin={{ top: 12, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid stroke={grid} vertical={false} />
        <XAxis dataKey="from_mw" tick={axis} tickLine={false} axisLine={false} interval={3} />
        <YAxis tick={axis} tickLine={false} axisLine={false} width={36} allowDecimals={false} />
        <ReferenceLine x={0} stroke={ink} strokeOpacity={0.4} />
        <Tooltip content={<Tip />} />
        <Bar dataKey="count" name="Hours" fill={ink} isAnimationActive={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export function ScatterChartView({ points }: { points: AccuracyPayload["scatter"] }) {
  if (points.length === 0) return null;
  const values = points.flatMap((point) => [point.forecast_mw, point.actual_mw]);
  const low = Math.min(...values);
  const high = Math.max(...values);
  const data = points.map((point) => ({ ...point, guide: point.forecast_mw }));
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart margin={{ top: 12, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid stroke={grid} />
        <XAxis
          dataKey="forecast_mw"
          type="number"
          name="Forecast"
          domain={[low, high]}
          tick={axis}
          tickLine={false}
          axisLine={false}
          tickFormatter={(value: number) => `${Math.round(value / 1000)}k`}
        />
        <YAxis
          dataKey="actual_mw"
          type="number"
          name="Outturn"
          domain={[low, high]}
          tick={axis}
          tickLine={false}
          axisLine={false}
          width={48}
          tickFormatter={(value: number) => `${Math.round(value / 1000)}k`}
        />
        <Tooltip content={<Tip />} />
        <Scatter data={data} dataKey="actual_mw" name="Outturn" fill={wind} fillOpacity={0.55} isAnimationActive={false} />
        <Line data={data} dataKey="guide" name="Equal line" stroke={ink} strokeDasharray="4 4" dot={false} isAnimationActive={false} legendType="none" />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
