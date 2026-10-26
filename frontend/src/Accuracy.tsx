import { useEffect, useState } from "react";
import { getJson } from "./api";
import { DailyErrorChart, HistogramChart, HourBiasChart, ScatterChartView, VintageChart } from "./charts";
import { energy, mw, pct, signedEnergy, signedMw } from "./format";
import type { AccuracyPayload } from "./types";

type Props = {
  auction: string;
  buffer: number;
  onOpenDay: (delivery: string) => void;
};

export function Accuracy({ auction, buffer, onOpenDay }: Props) {
  const [data, setData] = useState<AccuracyPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getJson<AccuracyPayload>(`/api/accuracy?auction=${auction}&buffer_min=${buffer}`)
      .then((payload) => {
        if (!cancelled) {
          setData(payload);
          setError(null);
        }
      })
      .catch((reason: Error) => {
        if (!cancelled) setError(reason.message);
      });
    return () => {
      cancelled = true;
    };
  }, [auction, buffer]);

  if (error) return <p className="error">{error}</p>;
  if (!data || !data.forecast) return <p className="card status">Scoring the gate-time file against FUELHH wind.</p>;

  const skill = data.skill_vs_persistence;
  const skillClass = skill == null ? "" : skill > 0.02 ? "good" : skill < -0.02 ? "short" : "";
  const biasClass = data.forecast.bias_mw > 25 ? "short" : data.forecast.bias_mw < -25 ? "long" : "";

  return (
    <div className="stack">
      <section className="card memo">
        {data.narrative.map((paragraph) => (
          <p key={paragraph}>{paragraph}</p>
        ))}
      </section>

      <section className="stats">
        <article className="card stat">
          <div className="k">MAE</div>
          <div className="v">{mw(data.forecast.mae_mw)}</div>
          <div className="s">{pct(data.forecast.wape)} of outturn energy · {data.sample.hours} hours</div>
        </article>
        <article className={`card stat ${biasClass}`}>
          <div className="k">Bias</div>
          <div className="v">{signedMw(data.forecast.bias_mw)}</div>
          <div className="s">forecast minus actual · positive is short</div>
        </article>
        <article className="card stat">
          <div className="k">RMSE</div>
          <div className="v">{mw(data.forecast.rmse_mw)}</div>
          <div className="s">mean outturn {mw(data.forecast.mean_actual_mw)}</div>
        </article>
        <article className={`card stat ${skillClass}`}>
          <div className="k">Skill vs persistence</div>
          <div className="v">{skill == null ? "—" : skill.toFixed(2)}</div>
          <div className="s">persistence MAE {data.persistence ? mw(data.persistence.mae_mw) : "—"}</div>
        </article>
      </section>

      <section className="card callout">
        <h2>Using the error in a bid</h2>
        <p className="hint">
          A positive error is energy the day-ahead book did not buy and would have to find later. These haircuts describe January.
          The held-out row is the one that was not fit on the days it scores.
        </p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th className="left">Rule</th>
                <th>Haircut</th>
                <th>Extra buy</th>
                <th>Shortfall left</th>
                <th>Shortfall with no haircut</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="left">Remove the month’s average bias</td>
                <td>{mw(data.shortfall.haircut_bias_mw)}</td>
                <td>{energy(data.shortfall.extra_buy_bias_mwh)}</td>
                <td>{energy(data.shortfall.uncovered_after_bias_mwh)}</td>
                <td>{energy(data.shortfall.raw_positive_mwh)}</td>
              </tr>
              <tr>
                <td className="left">Cover 90% of hours, same month</td>
                <td>{mw(data.shortfall.haircut_p90_mw)}</td>
                <td>{energy(data.shortfall.extra_buy_p90_mwh)}</td>
                <td>{energy(data.shortfall.uncovered_after_p90_mwh)}</td>
                <td>{energy(data.shortfall.raw_positive_mwh)}</td>
              </tr>
              <tr>
                <td className="left">90% haircut fit on 1–21 Jan, scored on 22–31 Jan</td>
                <td>{mw(data.holdout.fit_p90_signed_mw)}</td>
                <td>{energy(data.holdout.test_extra_buy_mwh)}</td>
                <td>{energy(data.holdout.test_uncovered_mwh)}</td>
                <td>{energy(data.holdout.test_raw_positive_mwh)}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="hint">
          Absolute error stays within {mw(data.quantiles_abs_mw.p50)} for half of hours and within {mw(data.quantiles_abs_mw.p90)} for
          90% of hours. Held-out coverage of the 90% haircut was {pct(data.holdout.test_coverage_of_p90)}. {data.holdout.note}
        </p>
      </section>

      <section className="two">
        <article className="card panel">
          <h2>Daily energy error</h2>
          <p className="hint">Positive (rust) means the day was short against the file. Open a day from the table below.</p>
          <div className="legend">
            <span><i className="swatch-short" /> Short</span>
            <span><i className="swatch-long" /> Long</span>
          </div>
          <div className="chart short">
            <DailyErrorChart days={data.by_day} />
          </div>
        </article>
        <article className="card panel">
          <h2>Bias by hour</h2>
          <p className="hint">London clock hour. The same sign convention: positive means the file was high.</p>
          <div className="chart short">
            <HourBiasChart hours={data.by_hour} />
          </div>
        </article>
      </section>

      <section className="two">
        <article className="card panel">
          <h2>MAE by publication clock</h2>
          <p className="hint">Decision-day runs only. Solid bars were available at the selected gate. Faded bars were not.</p>
          <div className="legend">
            <span><i className="swatch-wind" /> Before the gate</span>
            <span><i className="swatch-faint" /> After the gate</span>
          </div>
          <div className="chart short">
            <VintageChart rows={data.by_vintage} />
          </div>
        </article>
        <article className="card panel">
          <h2>Error distribution</h2>
          <p className="hint">Hours, in 200 MW bins of forecast minus actual. Correlation {data.correlation?.toFixed(2) ?? "—"}.</p>
          <div className="chart short">
            <HistogramChart bins={data.histogram} />
          </div>
        </article>
      </section>

      <section className="card panel">
        <h2>File against outturn</h2>
        <p className="hint">Each point is one clock hour. The dashed line is a perfect file. Axes are in MW, labelled in thousands.</p>
        <div className="chart">
          <ScatterChartView points={data.scatter} />
        </div>
      </section>

      <section className="two">
        <article className="card panel">
          <h2>Error by forecast level</h2>
          <p className="hint">The top edge of a bin belongs to the next bin. The desk uses a bin only when it holds at least 24 hours.</p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th className="left">Forecast</th>
                  <th>Hours</th>
                  <th>MAE</th>
                  <th>Bias</th>
                  <th>P10</th>
                  <th>P90</th>
                </tr>
              </thead>
              <tbody>
                {data.by_level.map((row) => (
                  <tr key={row.label}>
                    <td className="left">{row.label}</td>
                    <td>{row.n}</td>
                    <td>{mw(row.mae_mw)}</td>
                    <td className={row.bias_mw > 0 ? "short" : "long"}>{signedMw(row.bias_mw)}</td>
                    <td>{signedMw(row.p10_mw)}</td>
                    <td>{signedMw(row.p90_mw)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
        <article className="card panel">
          <h2>Largest daily misses</h2>
          <p className="hint">By absolute energy error. Choosing a row opens that day with the outturn visible.</p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th className="left">Delivery</th>
                  <th>File</th>
                  <th>Error</th>
                  <th>MAE</th>
                  <th>Gate file</th>
                </tr>
              </thead>
              <tbody>
                {data.worst_days.map((day) => (
                  <tr key={day.delivery} className="clickable" onClick={() => onOpenDay(day.delivery)}>
                    <td className="left">
                      {day.weekday} {day.label}
                    </td>
                    <td>{energy(day.forecast_mwh)}</td>
                    <td className={day.error_mwh > 0 ? "short" : "long"}>{signedEnergy(day.error_mwh)}</td>
                    <td>{mw(day.mae_mw)}</td>
                    <td>{day.publish_local}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      </section>

      <section className="card panel">
        <h2>Publication clocks on the decision day</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th className="left">London</th>
                <th>At this gate</th>
                <th>Days</th>
                <th>MAE</th>
                <th>Bias</th>
                <th>Hours before delivery</th>
              </tr>
            </thead>
            <tbody>
              {data.by_vintage.map((row) => (
                <tr key={row.slot_local}>
                  <td className="left">{row.slot_local}</td>
                  <td>{row.before_gate ? "Yes" : "No"}</td>
                  <td>{row.n_days}</td>
                  <td>{mw(row.mae_mw)}</td>
                  <td className={row.bias_mw > 0 ? "short" : "long"}>{signedMw(row.bias_mw)}</td>
                  <td>{row.lead_to_midnight_h.toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
