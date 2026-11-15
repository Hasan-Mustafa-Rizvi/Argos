import { Plate } from "@/components/argos/Plate"
import type { FamilyIncident } from "@/data/contract"
import { checksToday, endingLabel, ENDING_NAMES, ENDINGS, formatClock, triggerLabel } from "@/data/derive"
import { solutions } from "@/content/landing"

const ROMAN = ["I", "II", "III", "IV"]

function firstSentence(text: string) {
  const end = text.indexOf(". ")
  return end === -1 ? text : text.slice(0, end + 1)
}

export interface FamilyPlatesProps {
  incidents: readonly FamilyIncident[]
  person: string
  now: number
}

/** Family sees Last check, Today and What Argos does where a clinician sees sensor plates. */
export function FamilyPlates({ incidents, person, now }: FamilyPlatesProps) {
  const last = incidents[0]
  const today = checksToday(incidents, now)
  const counts = ENDINGS.map((ending) => [ending, today.filter((i) => i.status === ending).length] as const).filter(
    ([, n]) => n > 0,
  )

  return (
    <>
      <Plate label="Last check" wrapClassName="argos-area-a">
        {last ? (
          <div className="argos-last">
            <p className="argos-last-title">{triggerLabel(last.trigger)}</p>
            <p className="argos-mono argos-last-when">{formatClock(last.started_at)}</p>
            <p>{endingLabel(last, person)}</p>
          </div>
        ) : (
          <p className="argos-empty">No checks yet.</p>
        )}
      </Plate>

      <Plate label="Today" wrapClassName="argos-area-b">
        {today.length ? (
          <div className="argos-today">
            <p className="argos-gauge-value">
              {today.length}
              <span className="argos-gauge-unit">{today.length === 1 ? "check" : "checks"}</span>
            </p>
            <ul className="argos-today-list">
              {counts.map(([ending, n]) => (
                <li key={ending}>
                  <span className="argos-mono">{n}</span> {ENDING_NAMES[ending]}
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="argos-empty">No checks yet.</p>
        )}
      </Plate>

      <Plate label="What Argos does" wrapClassName="argos-area-c">
        <ol className="argos-steps">
          {solutions.map((step, i) => (
            <li key={step.title}>
              <span className="argos-ledger-num">{ROMAN[i]}.</span>
              <span>
                <b>{step.title}.</b> {firstSentence(step.body)}
              </span>
            </li>
          ))}
        </ol>
      </Plate>
    </>
  )
}
