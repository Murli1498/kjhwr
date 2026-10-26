import { useEffect, useState } from "react";
import { getJson } from "./api";
import { Accuracy } from "./Accuracy";
import { Desk } from "./Desk";
import { Method } from "./Method";
import type { Calendar, Meta } from "./types";

type View = "desk" | "accuracy" | "method";
type Context = "prior" | "retrospective";

type State = {
  view: View;
  delivery: string;
  auction: string;
  buffer: number;
  outturn: boolean;
  context: Context;
};

const BUFFERS = [
  { value: 0, label: "None", note: "file at the gate counts" },
  { value: 15, label: "15 min", note: "time to submit" },
  { value: 30, label: "30 min", note: "rebuild the stack" },
];

function readState(): State {
  const params = new URLSearchParams(window.location.search);
  const view = params.get("view");
  const buffer = Number(params.get("buffer") ?? "0");
  return {
    view: view === "accuracy" || view === "method" ? view : "desk",
    delivery: params.get("date") ?? "",
    auction: params.get("auction") ?? "n2ex",
    buffer: [0, 15, 30].includes(buffer) ? buffer : 0,
    outturn: params.get("outturn") === "1",
    context: params.get("context") === "retrospective" ? "retrospective" : "prior",
  };
}

export function App() {
  const [state, setState] = useState<State>(readState);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [calendar, setCalendar] = useState<Calendar | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getJson<Meta>("/api/meta").then(setMeta).catch((reason: Error) => setError(reason.message));
  }, []);

  useEffect(() => {
    let cancelled = false;
    getJson<Calendar>(`/api/calendar?auction=${state.auction}&buffer_min=${state.buffer}`)
      .then((data) => {
        if (cancelled) return;
        setCalendar(data);
        setState((current) => (current.delivery ? current : { ...current, delivery: data.spotlight.delivery }));
      })
      .catch((reason: Error) => setError(reason.message));
    return () => {
      cancelled = true;
    };
  }, [state.auction, state.buffer]);

  useEffect(() => {
    const params = new URLSearchParams();
    params.set("view", state.view);
    if (state.delivery) params.set("date", state.delivery);
    params.set("auction", state.auction);
    params.set("buffer", String(state.buffer));
    if (state.outturn) params.set("outturn", "1");
    if (state.context === "retrospective") params.set("context", "retrospective");
    window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
  }, [state]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (!calendar || (event.key !== "ArrowLeft" && event.key !== "ArrowRight")) return;
      const target = event.target;
      if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement) return;
      const index = calendar.days.findIndex((day) => day.delivery === state.delivery);
      if (index < 0) return;
      const next = index + (event.key === "ArrowRight" ? 1 : -1);
      const day = calendar.days[next];
      if (!day) return;
      event.preventDefault();
      setState((current) => ({ ...current, delivery: day.delivery, view: "desk" }));
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [calendar, state.delivery]);

  const auctions = meta?.auctions ?? [];

  return (
    <div className="app">
      <header>
        <p className="kicker">Pilot · GB day-ahead · Operational wind · January 2026</p>
        <div className="title-row">
          <div>
            <h1>Windgate</h1>
            <p className="lede">
              The wind file a buyer could have used at the day-ahead gate, and how far that file sat from the outturn.
            </p>
          </div>
          <nav aria-label="Sections">
            <button aria-pressed={state.view === "desk"} onClick={() => setState((current) => ({ ...current, view: "desk" }))}>
              Desk
            </button>
            <button
              aria-pressed={state.view === "accuracy"}
              onClick={() => setState((current) => ({ ...current, view: "accuracy" }))}
            >
              Accuracy
            </button>
            <button
              aria-pressed={state.view === "method"}
              onClick={() => setState((current) => ({ ...current, view: "method" }))}
            >
              Method
            </button>
          </nav>
        </div>
        <p className="boundary">
          Operationally metered GB wind only, from Elexon FUELHH and WINDFOR. Embedded wind is outside both series.
          The forecast is hourly. One megawatt-hour of wind error moves the residual buy by one megawatt-hour. Demand and
          prices are not in this pilot.
        </p>
      </header>

      {state.view !== "method" ? (
        <div className="toolbar">
          <div className="segment" role="group" aria-label="Auction">
            <span>Auction gate</span>
            {auctions.map((auction) => (
              <button
                key={auction.id}
                aria-pressed={state.auction === auction.id}
                onClick={() => setState((current) => ({ ...current, auction: auction.id }))}
              >
                {auction.name}
                <small>{auction.gate_local} London</small>
              </button>
            ))}
          </div>
          <div className="segment" role="group" aria-label="Preparation buffer">
            <span>Preparation buffer</span>
            {BUFFERS.map((buffer) => (
              <button
                key={buffer.value}
                aria-pressed={state.buffer === buffer.value}
                onClick={() => setState((current) => ({ ...current, buffer: buffer.value }))}
              >
                {buffer.label}
                <small>{buffer.note}</small>
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {error ? <p className="error">{error}</p> : null}

      {state.view === "desk" ? (
        state.delivery ? (
          <Desk
            delivery={state.delivery}
            auction={state.auction}
            buffer={state.buffer}
            outturn={state.outturn}
            context={state.context}
            calendar={calendar}
            onDelivery={(delivery) => setState((current) => ({ ...current, delivery }))}
            onOutturn={(outturn) => setState((current) => ({ ...current, outturn }))}
            onContext={(context) => setState((current) => ({ ...current, context }))}
          />
        ) : (
          <p className="status">Choosing a delivery day from the January files.</p>
        )
      ) : null}

      {state.view === "accuracy" ? (
        <Accuracy
          auction={state.auction}
          buffer={state.buffer}
          onOpenDay={(delivery) => setState((current) => ({ ...current, view: "desk", delivery, outturn: true }))}
        />
      ) : null}

      {state.view === "method" ? <Method /> : null}

      <footer className="footer">
        <span>{meta ? `Elexon snapshot ${meta.fetched_at}. ${meta.timezone_note}` : "Loading snapshot."}</span>
        <span>Arrow keys move the delivery day.</span>
      </footer>
    </div>
  );
}
