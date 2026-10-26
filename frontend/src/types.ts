export type Auction = {
  id: string;
  name: string;
  gate_local: string;
  product: string;
  detail: string;
};

export type Meta = {
  product: string;
  fetched_at: string;
  window_label: string;
  actual_rows: number;
  forecast_rows: number;
  publications: number;
  timezone_note: string;
  auctions: Auction[];
  sources: string[];
};

export type CalendarDay = {
  delivery: string;
  weekday: string;
  weekday_index: number;
  day: number;
  forecast_mwh: number | null;
  revision_mwh: number | null;
  publish_local: string | null;
  publish_date: string | null;
};

export type Calendar = {
  auction: Auction;
  buffer_min: number;
  days: CalendarDay[];
  spotlight: {
    delivery: string;
    auction: string;
    buffer_min: number;
    revision_mwh: number | null;
    reason: string;
  };
};

export type HourRow = {
  start_utc: string;
  label: string;
  hour_local: number;
  sp_start: number;
  sp_end: number;
  forecast_mw: number;
  actual_sp1_mw: number | null;
  actual_sp2_mw: number | null;
  actual_mw: number | null;
  error_mw: number | null;
  band_low_mw: number | null;
  band_high_mw: number | null;
  debiased_mw: number | null;
};

export type Vintage = {
  publish_utc: string;
  publish_local: string;
  publish_date: string;
  day_offset_label: string;
  available: boolean;
  locked: boolean;
  forecast_mwh: number;
  delta_vs_locked_mwh: number | null;
  minutes_before_deadline: number;
};

export type DeskPayload = {
  delivery: string;
  delivery_label: string;
  weekday: string;
  auction: Auction;
  buffer_min: number;
  context: "prior" | "retrospective";
  deadline_utc: string;
  deadline_local: string;
  deadline_date_label: string;
  vintage: null | {
    publish_utc: string;
    publish_local: string;
    publish_date: string;
    publish_date_label: string;
    minutes_before_deadline: number;
  };
  hours: HourRow[];
  totals: {
    forecast_mwh: number | null;
    forecast_mean_mw: number | null;
    forecast_min_mw: number | null;
    forecast_max_mw: number | null;
    actual_mwh: number | null;
    error_mwh: number | null;
    paired_hours: number;
    forecast_hours: number;
    debiased_mwh: number | null;
  };
  vintages: Vintage[];
  previous: null | {
    publish_utc: string;
    publish_local: string;
    forecast_mwh: number;
    delta_mwh: number | null;
  };
  comparison: null | {
    auction_id: string;
    auction_name: string;
    gate_local: string;
    publish_utc: string | null;
    publish_local: string | null;
    forecast_mwh: number | null;
    delta_mwh: number | null;
    same_file: boolean;
  };
  band: null | {
    basis: string;
    hours_used: number;
    days_used: number;
    global_bias_mw: number;
    note: string;
  };
  narrative: string[];
};

export type MetricBlock = {
  n: number;
  mae_mw: number;
  rmse_mw: number;
  bias_mw: number;
  wape: number | null;
  mean_forecast_mw: number;
  mean_actual_mw: number;
  energy_error_mwh: number;
};

export type DayStat = {
  delivery: string;
  label: string;
  weekday: string;
  hours: number;
  forecast_mwh: number;
  actual_mwh: number;
  error_mwh: number;
  mae_mw: number;
  bias_mw: number;
  publish_local: string;
};

export type AccuracyPayload = {
  auction: Auction;
  buffer_min: number;
  sample: {
    hours: number;
    days: number;
    missing_days: string[];
    missing_hours: number;
    persistence_hours: number;
  };
  forecast: MetricBlock;
  persistence: MetricBlock | null;
  skill_vs_persistence: number | null;
  correlation: number | null;
  within_hour_span_mw: number | null;
  within_hour_unresolved_mw: number | null;
  quantiles_abs_mw: { p50: number; p80: number; p90: number; p95: number };
  quantiles_signed_mw: { p10: number; p50: number; p90: number };
  shortfall: {
    raw_positive_mwh: number;
    share_hours_short: number;
    haircut_bias_mw: number;
    extra_buy_bias_mwh: number;
    uncovered_after_bias_mwh: number;
    haircut_p90_mw: number;
    extra_buy_p90_mwh: number;
    uncovered_after_p90_mwh: number;
    hours_covered_by_p90: number;
  };
  holdout: {
    fit_label: string;
    test_label: string;
    fit_hours?: number;
    test_hours: number;
    fit_days?: number;
    test_days?: number;
    fit_bias_mw?: number;
    fit_p90_signed_mw?: number;
    test_mae_raw_mw?: number;
    test_mae_debiased_mw?: number;
    test_coverage_of_p90?: number;
    test_raw_positive_mwh?: number;
    test_uncovered_mwh?: number;
    test_extra_buy_mwh?: number;
    note: string;
  };
  by_day: DayStat[];
  by_hour: { hour_local: number; label: string; n: number; mae_mw: number; bias_mw: number; mean_actual_mw: number }[];
  by_vintage: {
    slot_local: string;
    before_gate: boolean;
    n_days: number;
    n_hours: number;
    mae_mw: number;
    bias_mw: number;
    lead_to_midnight_h: number;
  }[];
  by_level: {
    label: string;
    lo_mw: number;
    hi_mw: number;
    n: number;
    mae_mw: number;
    bias_mw: number;
    p10_mw: number;
    p90_mw: number;
  }[];
  histogram: { from_mw: number; to_mw: number; label: string; count: number }[];
  scatter: { forecast_mw: number; actual_mw: number }[];
  worst_days: DayStat[];
  narrative: string[];
};
