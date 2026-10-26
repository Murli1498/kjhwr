export function Method() {
  return (
    <article className="prose">
      <h2>The decision this desk is built for</h2>
      <p>
        A GB supplier buying for its customers has to be in the day-ahead auctions before those auctions close, which is
        the morning before delivery. Wind that the supplier can count on reduces the volume it has to buy. Wind it cannot
        count on comes back as a short or a long position in later markets. This pilot shows only that wind term.
        Residual volume is demand minus wind minus everything else, and demand is out of scope, so the desk never prints
        a buy quantity. It prints the wind the buyer could have subtracted, and the error in that subtraction. One
        megawatt of error for one hour is one megawatt-hour of residual error.
      </p>
      <h2>What is in the two series</h2>
      <p>
        Actuals are Elexon FUELHH, fuel type WIND. Elexon describes that field as average megawatts over the half-hour,
        from operational metering on transmission-connected wind. Forecasts are Elexon WINDFOR. The current-forecast
        documentation describes the same population: wind farms visible to the system operator, with operational metering,
        updated up to eight times a day. In this January extract the runs land at 02:30, 04:30, 07:30, 09:30, 11:30,
        15:30, 18:30 and 22:30 UTC, which is also London time because the month is GMT. Each run is 73 hourly points.
        The generation field is treated as average megawatts for that clock hour. Elexon is explicit about the half-hour
        average on FUELHH and is not equally explicit on WINDFOR; the values are the same order of magnitude and the
        same metered population, which is why they are scored against each other.
      </p>
      <p>
        Elexon’s own generation-by-fuel note says this view of wind leaves out embedded generation and farms without
        operational meters, and that in 2025 the operational-meter share was about 82%. This product is not total GB
        wind. Adding an embedded estimate would be a different comparison, and that estimate is not in the two datasets
        the pilot is allowed to use.
      </p>
      <h2>Which file is locked</h2>
      <p>
        A file is usable when its publish time is at or before the auction gate, minus any preparation buffer. Among
        usable files, the desk takes the latest one that contains every clock hour of the delivery day. A file that
        stops short of the last hour is skipped, even if it is newer. The buffer is there because a file timestamped at
        09:30 is not the same thing as a bid that can be rebuilt by 09:30. With no buffer, the January N2EX book locks
        the 09:30 run, twenty minutes before the 09:50 gate. EPEX hourly closes at 09:20, so it locks the 07:30 run. The
        half-hourly EPEX auction closes at 15:30, and the 15:30 run is timestamped on the gate itself; fifteen minutes
        of buffer drops it.
      </p>
      <p>
        Gates used here are the published order-book closures, applied in Europe/London: N2EX 09:50, EPEX GB 60-minute
        09:20, EPEX GB 30-minute 15:30. January has no clock change, so London and UTC match. The deadline function still
        uses the London zone, which matters if the same rule is ever pointed at a summer day.
      </p>
      <h2>How an hour is scored</h2>
      <pre className="formula">{`error = forecast − actual
actual = (settlement period + next settlement period) / 2
MAE = mean of |error|
bias = mean of error
RMSE = square root of mean of error²
WAPE = sum of |error| / sum of actual
skill = 1 − MAE of the file / MAE of persistence`}</pre>
      <p>
        Positive error means the file was above the outturn. The buyer who subtracted the file from demand is short, and
        has to buy the difference later. Negative error means the buyer is long. Persistence is the previous day’s
        outturn for the same clock hour, which is why 30 December is in the actuals even though it is not a scored
        delivery day. MAPE is not used. Hours with little wind make a percentage explode, and a buyer’s risk is in
        megawatt-hours.
      </p>
      <p>
        The two half-hours inside a clock hour are not given different forecasts. Their average absolute difference is
        reported beside the hourly MAE so it is obvious whether the miss is the hour itself or the shape the hourly file
        cannot see. Settlement-period numbers are the ordinary 1-to-48 numbering of a 24-hour London day. The pilot month
        has no 23-hour or 25-hour day. The hour generator does know about those days; the API simply refuses delivery
        dates outside January 2026.
      </p>
      <h2>The band and the haircut</h2>
      <p>
        The shaded band is the 10th to 90th percentile of historical error, chosen inside a forecast-level bin when that
        bin has at least 24 hours, and from the whole sample otherwise. “Earlier days only” uses delivery days before
        the one on screen, which is the sample a desk would have had. “All of January” includes the future of that day
        and is labelled as retrospective. Fewer than 48 earlier hours draws no band. Quantiles are nearest-rank:
        ceil(p × n).
      </p>
      <p>
        A haircut subtracts a fixed number of megawatts from the wind the buyer relies on, which means buying that many
        extra megawatt-hours every hour. The 90% haircut is the 90th percentile of signed error, floored at zero. Fit on
        the same hours it is scored on, it covers at least 90% of those hours by construction. That number is shown so
        the cost of the cover is visible, and it is not offered as a policy. The row that matters is the one fit on 1–21
        January and scored on 22–31 January without refitting. One split of one month is a check against fooling
        ourselves, not an out-of-year backtest.
      </p>
      <h2>What the code does on purpose</h2>
      <ul>
        <li>The running app reads a snapshot. It does not call Elexon on a page view, so a review does not depend on BMRS being up, and the January numbers do not move under a reviewer.</li>
        <li>scripts/fetch_elexon.py is the only place that talks to the stream endpoints. It records when it ran.</li>
        <li>Gate selection, the hourly join, the metrics, the haircut and the holdout split are pure functions with tests. The narrative is filled from those numbers.</li>
        <li>Publication clocks are discovered from the files. On 15 January the late-morning run is 12:25 rather than 11:30. It stays its own slot. It is after both morning gates.</li>
        <li>There is no demand, no price, no other fuel, and no embedded-wind estimate. Those would change the answer and they are outside the data this pilot is allowed to use.</li>
      </ul>
      <h2>Sources</h2>
      <ul>
        <li><a href="https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream">Elexon FUELHH stream</a></li>
        <li><a href="https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream">Elexon WINDFOR stream</a></li>
        <li><a href="https://bmrs.elexon.co.uk/api-documentation/endpoint/forecast/generation/wind">Elexon description of the wind forecast population and the eight daily runs</a></li>
        <li><a href="https://bmrs.elexon.co.uk/generation-by-fuel-type">Elexon generation by fuel type, including the embedded-wind caveat</a></li>
        <li><a href="https://support.nordpoolgroup.com/support/solutions/articles/8000088463-about-the-n2ex-day-ahead-auction">Nord Pool, N2EX day-ahead gate at 09:50 London</a></li>
        <li><a href="https://www.epexspot.com/en/tradingproducts">EPEX SPOT trading products: GB 60-minute gate 09:20, GB 30-minute gate 15:30</a></li>
      </ul>
    </article>
  );
}
