import { Plate } from "@/components/argos/Plate"
import type { TimelineEvent } from "@/data/contract"
import { formatClock } from "@/data/derive"

import { printSentence } from "./sentence"

/** Newest first: the time in mono, then the sentence the record carries, whatever its kind. */
export function TimelinePlate({ events, wrapClassName }: { events: readonly TimelineEvent[]; wrapClassName?: string }) {
  return (
    <Plate label="Timeline" wrapClassName={wrapClassName}>
      {events.length ? (
        <ol className="argos-timeline" aria-label="Timeline, newest first">
          {events.map((event) => (
            <li key={event.id}>
              <time dateTime={event.at}>{formatClock(event.at)}</time>
              <span>{printSentence(event.text)}</span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="argos-empty">Nothing has happened yet.</p>
      )}
    </Plate>
  )
}
