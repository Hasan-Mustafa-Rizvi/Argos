/**
 * Stands in for the one stored image of an escalated incident. The scripted run points at no
 * real file, so this says plainly that it is a placeholder.
 */
export function SnapshotPlaceholder({ tone = "paper" }: { tone?: "paper" | "night" }) {
  return (
    <figure className="argos-snapshot" data-tone={tone} data-testid="snapshot-placeholder">
      <div className="argos-snapshot-frame" aria-hidden="true">
        <div className="argos-hatch argos-snapshot-hatch" />
      </div>
      <figcaption>
        <span className="argos-label">Snapshot · placeholder</span>
        <span>The scripted run has no real image.</span>
      </figcaption>
    </figure>
  )
}
