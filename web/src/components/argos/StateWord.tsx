import { STATE_WORDS, type InkState } from "./ink"

/** The state in display type: the largest words on the dashboard. */
export function StateWord({ state }: { state: InkState }) {
  return (
    <p className="argos-state-word" aria-live="polite">
      {STATE_WORDS[state]}
    </p>
  )
}
