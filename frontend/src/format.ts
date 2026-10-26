export function mw(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${Math.round(value).toLocaleString("en-GB")} MW`;
}

export function signedMw(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  const whole = Math.round(value);
  const body = Math.abs(whole).toLocaleString("en-GB");
  if (whole > 0) return `+${body} MW`;
  if (whole < 0) return `−${body} MW`;
  return "0 MW";
}

export function energy(mwh: number | null | undefined): string {
  if (mwh == null || Number.isNaN(mwh)) return "—";
  const whole = Math.round(mwh);
  const sign = whole < 0 ? "−" : "";
  const mag = Math.abs(whole);
  if (mag >= 1000) return `${sign}${(mag / 1000).toFixed(1).replace(/\.0$/, "")} GWh`;
  return `${sign}${mag.toLocaleString("en-GB")} MWh`;
}

export function signedEnergy(mwh: number | null | undefined): string {
  if (mwh == null || Number.isNaN(mwh)) return "—";
  const whole = Math.round(mwh);
  if (whole > 0) return `+${energy(whole)}`;
  return energy(whole);
}

export function pct(fraction: number | null | undefined, digits = 1): string {
  if (fraction == null || Number.isNaN(fraction)) return "—";
  return `${(fraction * 100).toFixed(digits)}%`;
}

export function positionWord(error: number | null | undefined): string {
  if (error == null) return "";
  if (error > 25) return "short";
  if (error < -25) return "long";
  return "flat";
}
