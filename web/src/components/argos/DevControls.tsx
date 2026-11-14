import { Button } from "@/components/ui/button"

import { INK_STATES, STATE_WORDS, type InkState } from "./ink"

export interface ReplayDevControls {
  speed: number
  speeds: readonly number[]
  onSpeed: (speed: number) => void
  onRestart: () => void
}

export interface DevControlsProps {
  /** The forced state, or null to follow the data. */
  override: InkState | null
  onOverride: (state: InkState | null) => void
  replay?: ReplayDevControls
}

/** Shown only with ?dev=1. */
export function DevControls({ override, onOverride, replay }: DevControlsProps) {
  return (
    <aside className="argos-dev" aria-label="Developer controls">
      <p className="argos-label">Dev · state</p>
      <div className="argos-dev-row" role="group" aria-label="State override">
        <Button size="sm" variant="secondary" aria-pressed={override === null} onClick={() => onOverride(null)}>
          From data
        </Button>
        {INK_STATES.map((state) => (
          <Button
            key={state}
            size="sm"
            variant="secondary"
            aria-pressed={override === state}
            onClick={() => onOverride(state)}
          >
            {STATE_WORDS[state]}
          </Button>
        ))}
      </div>
      {replay && (
        <>
          <p className="argos-label">Dev · replay</p>
          <div className="argos-dev-row" role="group" aria-label="Replay speed">
            {replay.speeds.map((speed) => (
              <Button
                key={speed}
                size="sm"
                variant="secondary"
                aria-pressed={replay.speed === speed}
                onClick={() => replay.onSpeed(speed)}
              >
                {speed}×
              </Button>
            ))}
            <Button size="sm" variant="secondary" onClick={replay.onRestart}>
              Restart
            </Button>
          </div>
        </>
      )}
    </aside>
  )
}
