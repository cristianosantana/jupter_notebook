export function PipelineDots() {
  return (
    <div className="mb-2 flex gap-1.5" aria-hidden>
      {[0, 1, 2].map((d) => (
        <span
          key={d}
          className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-sky-500"
          style={{ animationDelay: `${d * 180}ms` }}
        />
      ))}
    </div>
  )
}
