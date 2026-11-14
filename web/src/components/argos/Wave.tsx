/** The running-dog wave that closes the dashboard. It tiles; it does not scale, and it does not go flat. */
export function Wave() {
  return (
    <div className="argos-wave argos-fade" aria-hidden="true">
      <div className="argos-wave-clip">
        <span className="argos-wave-run" />
      </div>
    </div>
  )
}
