import { useEffect, useState } from "react";
import { getJson } from "./api";
import { ProfileChart } from "./charts";
import { energy, mw, positionWord, signedEnergy, signedMw } from "./format";
import type { Calendar, DeskPayload } from "./types";

type Props = {
  delivery: string;
  auction: string;
  buffer: number;
  outturn: boolean;
  context: "prior" | "retrospective";
  calendar: Calendar | null;
  onDelivery: (delivery: string) => void;
  onOutturn: (outturn: boolean) => void;
  onContext: (context: "prior" | "retrospective") => void;
};

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function Desk({ delivery, auction, buffer, outturn, context, calendar, onDelivery, onOutturn, onContext }: Props) {
  const [data, setData] = useState<DeskPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const params = new URLSearchParams({
      delivery,
      auction,
      buffer_min: String(buffer),
      context,
    });
    getJson<DeskPayload>(`/api/desk?${params.toString()}`)
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
  }, [delivery, auction, buffer, context]);

  const maxEnergy = Math.max(1, ...(calendar?.days.map((day) => day.forecast_mwh ?? 0) ?? [1]));
  const leadingBlank = calendar ? calendar.days[0]?.weekday_index ?? 0 : 0;
  const current = data && data.delivery === delivery ? data : null;
  const totals = current?.totals;
  const errorClass = totals?.error_mwh != null && totals.error_mwh > 25 ? "short" : totals?.error_mwh != null && totals.error_mwh < -25 ? "long" : "";
  const maxVintage = Math.max(1, ...(current?.vintages.map((row) => row.forecast_mwh) ?? [1]));
  const csv = `/api/desk.csv?delivery=${delivery}&auction=${auction}&buffer_min=${buffer}&context=${context}`;

  return (
    <div className="desk-grid">
      <aside className="card calendar">
        <h2>January 2026</h2>
        <p className="hint">Bar height is the locked file’s daily energy. Gold outline is the largest pre-gate revision.</p>
        <div className="weekdays">
          {WEEKDAYS.map((day) => (
            <span key={day}>{day}</span>
          ))}
        </div>
        <div className="month">
          {Array.from({ length: leadingBlank }, (_, index) => (
            <span key={`pad-${index}`} />
          ))}
          {calendar?.days.map((day) => (
            <button
              key={day.delivery}
              className={day.delivery === calendar.spotlight.delivery ? "day spotlight" : "day"}
              aria-pressed={day.delivery === delivery}
              title={`${day.weekday} ${day.delivery}. Gate file ${day.publish_local ?? "unavailable"}. ${
                day.revision_mwh == null ? "" : `Last update ${energy(day.revision_mwh)}.`
              }`}
              onClick={() => onDelivery(day.delivery)}
            >
              <span className="day-num">{day.day}</span>
              <span className="day-bar" style={{ height: `${Math.max(8, ((day.forecast_mwh ?? 0) / maxEnergy) * 70)}%` }} />
            </button>
          ))}
        </div>
      </aside>

      <div className="stack">
        {error ? <p className="error">{error}</p> : null}
        {!current ? <p className="card status">Reading the gate file for this delivery day.</p> : null}
        {current ? (
          <>
            <section className="card memo">
              {current.narrative.map((paragraph) => (
                <p key={paragraph}>{paragraph}</p>
              ))}
            </section>

            <section className="stats">
              <article className="card stat">
                <div className="k">Wind in the file</div>
                <div className="v">{energy(totals?.forecast_mwh)}</div>
                <div className="s">across {totals?.forecast_hours ?? 0} hours</div>
              </article>
              <article className="card stat">
                <div className="k">Average</div>
                <div className="v">{mw(totals?.forecast_mean_mw)}</div>
                <div className="s">
                  {mw(totals?.forecast_min_mw)} to {mw(totals?.forecast_max_mw)}
                </div>
              </article>
              <article className="card stat">
                <div className="k">Move from previous file</div>
                <div className="v">{signedEnergy(current.previous?.delta_mwh)}</div>
                <div className="s">{current.previous ? `versus ${current.previous.publish_local}` : "no earlier full-day file"}</div>
              </article>
              <article className="card stat">
                <div className="k">After removing the bias</div>
                <div className="v">{energy(totals?.debiased_mwh)}</div>
                <div className="s">{current.band ? `${current.band.days_used} earlier days in the sample` : "no band yet"}</div>
              </article>
              <article className="card stat">
                <div className="k">Minutes before deadline</div>
                <div className="v">{current.vintage ? current.vintage.minutes_before_deadline : "—"}</div>
                <div className="s">
                  deadline {current.deadline_local} on {current.deadline_date_label}
                </div>
              </article>
            </section>

            {outturn && totals?.actual_mwh != null ? (
              <section className="stats">
                <article className="card stat">
                  <div className="k">Outturn</div>
                  <div className="v">{energy(totals.actual_mwh)}</div>
                  <div className="s">{totals.paired_hours} paired hours</div>
                </article>
                <article className={`card stat ${errorClass}`}>
                  <div className="k">Energy error</div>
                  <div className="v">{signedEnergy(totals.error_mwh)}</div>
                  <div className="s">
                    {positionWord(totals.error_mwh) === "short"
                      ? "file above outturn · buy more later"
                      : positionWord(totals.error_mwh) === "long"
                        ? "file below outturn · bought too much"
                        : "close to flat on the day"}
                  </div>
                </article>
              </section>
            ) : null}

            <section className="card panel">
              <div className="panel-head">
                <div>
                  <h2>{current.weekday} {current.delivery_label}</h2>
                  <p className="hint">Half-hours. The forecast is held flat across each clock hour.</p>
                </div>
                <div className="segment" role="group" aria-label="What to show">
                  <button aria-pressed={!outturn} onClick={() => onOutturn(false)}>
                    At the gate
                  </button>
                  <button aria-pressed={outturn} onClick={() => onOutturn(true)}>
                    With outturn
                  </button>
                </div>
              </div>
              <div className="legend">
                <span><i className="swatch-wind" /> Forecast</span>
                {current.band ? <span><i className="swatch-band" /> 10th–90th error band</span> : null}
                {outturn ? <span><i className="swatch-ink" /> Half-hourly outturn</span> : null}
              </div>
              <div className="chart">
                <ProfileChart hours={current.hours} showOutturn={outturn} />
              </div>
              <div className="row-between">
                <div className="segment" role="group" aria-label="Error band sample">
                  <button aria-pressed={context === "prior"} onClick={() => onContext("prior")}>
                    Band from earlier days
                  </button>
                  <button aria-pressed={context === "retrospective"} onClick={() => onContext("retrospective")}>
                    Band from all of January
                  </button>
                </div>
                <a href={csv}>Download this day</a>
              </div>
              {current.band ? <p className="hint">{current.band.note}</p> : null}
            </section>

            <section className="card panel">
              <div className="panel-head">
                <div>
                  <h2>Files around the gate</h2>
                  <p className="hint">Daily energy in each publication that covers this delivery day. After the deadline, the file is no longer a day-ahead input.</p>
                </div>
              </div>
              <ol className="vintages">
                {current.vintages.map((row) => (
                  <li key={row.publish_utc} className={row.locked ? "locked" : row.available ? "open" : "late"}>
                    <span>{row.publish_local}</span>
                    <span className="when">{row.day_offset_label}</span>
                    <span className="track">
                      <span style={{ width: `${(row.forecast_mwh / maxVintage) * 100}%` }} />
                    </span>
                    <span>{energy(row.forecast_mwh)}</span>
                    <span className="flag">{row.locked ? "Locked" : row.available ? "Available" : "After gate"}</span>
                  </li>
                ))}
              </ol>
            </section>

            <section className="card panel">
              <div className="panel-head">
                <div>
                  <h2>Settlement periods</h2>
                  <p className="hint">
                    {outturn
                      ? "Short means the outturn was below the file. The buyer would have needed more energy later."
                      : "Outturn columns stay hidden until you ask for them. They were not known at the gate."}
                  </p>
                </div>
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th className="left">Hour</th>
                      <th>SP</th>
                      <th>Forecast</th>
                      <th>Debiased</th>
                      <th>Band low</th>
                      <th>Band high</th>
                      {outturn ? (
                        <>
                          <th>First half</th>
                          <th>Second half</th>
                          <th>Hour</th>
                          <th>Error</th>
                        </>
                      ) : null}
                    </tr>
                  </thead>
                  <tbody>
                    {current.hours.map((hour) => (
                      <tr key={hour.start_utc}>
                        <td className="left">{hour.label}</td>
                        <td>
                          {hour.sp_start}–{hour.sp_end}
                        </td>
                        <td>{mw(hour.forecast_mw)}</td>
                        <td>{mw(hour.debiased_mw)}</td>
                        <td>{mw(hour.band_low_mw)}</td>
                        <td>{mw(hour.band_high_mw)}</td>
                        {outturn ? (
                          <>
                            <td>{mw(hour.actual_sp1_mw)}</td>
                            <td>{mw(hour.actual_sp2_mw)}</td>
                            <td>{mw(hour.actual_mw)}</td>
                            <td className={positionWord(hour.error_mw)}>
                              {signedMw(hour.error_mw)}
                              {positionWord(hour.error_mw) === "flat" ? null : <em className="word">{positionWord(hour.error_mw)}</em>}
                            </td>
                          </>
                        ) : null}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        ) : null}
      </div>
    </div>
  );
}
