import { PIPELINE_STEPS } from '../../chat/constants'
import { PipelineDots } from './PipelineDots'

export function PipelineStatusBlock({
  stepIndex,
  compact,
}: {
  stepIndex: number
  compact?: boolean
}) {
  const label = PIPELINE_STEPS[stepIndex % PIPELINE_STEPS.length]
  if (compact) {
    return (
      <div className="pipeline-compact">
        <PipelineDots />
        <p className="font-medium leading-snug text-slate-300">{label}</p>
      </div>
    )
  }
  return (
    <div className="flex justify-start">
      <div className="pipeline-card">
        <PipelineDots />
        <p className="text-sm font-medium text-slate-700">{label}</p>
        <p className="mt-1.5 text-[11px] leading-snug text-slate-500">
          O assistente está a trabalhar — pode demorar alguns segundos.
        </p>
      </div>
    </div>
  )
}
