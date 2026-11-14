import { Plate } from "@/components/argos/Plate"
import { Sparkline } from "@/components/argos/Sparkline"
import { TickGauge } from "@/components/argos/TickGauge"
import type { Reading } from "@/data/contract"
import { formatClock } from "@/data/derive"

/* Gauge ranges are for drawing only; the numbers printed are the readings themselves. */
const STILL_MAX_S = 60
const ROOM_MIN_C = 10
const ROOM_MAX_C = 35

const one = (n: number) => n.toFixed(1)

/** A clinician sees Stillness, Room and Sensor history where family sees its own plates. */
export function ClinicianPlates({ readings }: { readings: readonly Reading[] }) {
  const latest = readings.at(-1)

  return (
    <>
      <Plate label="Stillness" wrapClassName="argos-area-a">
        {latest ? (
          <div className="argos-gauge">
            <p className="argos-gauge-value">
              {latest.still_s}
              <span className="argos-gauge-unit">s without moving</span>
            </p>
            <TickGauge
              value={latest.still_s}
              min={0}
              max={STILL_MAX_S}
              label={`${latest.still_s} seconds without moving, on a scale to ${STILL_MAX_S}`}
            />
            <p className="argos-gauge-note">
              {latest.person_present ? "A person is in view" : "No one is in view"} ·{" "}
              <span className="argos-mono">{formatClock(latest.at)}</span>
            </p>
          </div>
        ) : (
          <p className="argos-empty">No readings yet.</p>
        )}
      </Plate>

      <Plate label="Room" wrapClassName="argos-area-b">
        {latest ? (
          <div className="argos-gauge">
            <p className="argos-gauge-value">
              {latest.temp_c === null ? (
                <span className="argos-gauge-unit">Temperature not reported</span>
              ) : (
                <>
                  {one(latest.temp_c)}
                  <span className="argos-gauge-unit">°C</span>
                </>
              )}
            </p>
            <TickGauge
              value={latest.temp_c}
              min={ROOM_MIN_C}
              max={ROOM_MAX_C}
              label={
                latest.temp_c === null
                  ? "No temperature reading"
                  : `${one(latest.temp_c)} degrees, on a scale from ${ROOM_MIN_C} to ${ROOM_MAX_C}`
              }
            />
            <p className="argos-gauge-note">
              {latest.tilt_deg === null ? (
                "Tilt not reported"
              ) : (
                <>
                  Tilt <span className="argos-mono">{one(latest.tilt_deg)}°</span> from upright
                </>
              )}
            </p>
          </div>
        ) : (
          <p className="argos-empty">No readings yet.</p>
        )}
      </Plate>

      <Plate label="Sensor history" wrapClassName="argos-area-c">
        {readings.length ? (
          <div>
            <HistoryRow
              name="Stillness"
              unit=" s"
              values={readings.map((r) => r.still_s)}
              min={0}
              format={(v) => String(v)}
            />
            <HistoryRow name="Temperature" unit=" °C" values={readings.map((r) => r.temp_c)} format={one} />
            <HistoryRow name="Tilt" unit="°" values={readings.map((r) => r.tilt_deg)} min={0} format={one} />
          </div>
        ) : (
          <p className="argos-empty">No readings yet.</p>
        )}
      </Plate>
    </>
  )
}

function HistoryRow({
  name,
  unit,
  values,
  min,
  format,
}: {
  name: string
  /** Printed straight after the number, so it carries its own leading space if it needs one. */
  unit: string
  values: readonly (number | null)[]
  min?: number
  format: (v: number) => string
}) {
  const last = [...values].reverse().find((v): v is number => v !== null)
  return (
    <div className="argos-spark">
      <span className="argos-label">{name}</span>
      <Sparkline values={values} min={min} label={`${name} over the last ${values.length} readings`} />
      <span className="argos-mono">{last === undefined ? "Not reported" : `${format(last)}${unit}`}</span>
    </div>
  )
}
