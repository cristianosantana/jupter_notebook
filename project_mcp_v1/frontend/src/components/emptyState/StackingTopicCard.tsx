import { motion } from 'framer-motion'
import type { EmptyStateTopic } from './emptyStateTopics'
import { topicCardPreview } from './emptyStateTopics'

/**
 * Profundidade visual máxima no arco (evita sair do contentor com muitos tópicos).
 */
const MAX_VISUAL_DEPTH = 6
/** Deslocamento vertical por degrau — sensação de “descer” na roda. */
const Y_PER_STEP_PX = 26
/** Profundidade (translateZ negativo = afastar na roda). */
const Z_PER_STEP_PX = -36
/** Inclinação em graus por degrau (topo do cartão afasta-se = vai para trás da roda). */
const ROTATE_X_PER_STEP = 12

type StackingTopicCardProps = {
  topic: EmptyStateTopic
  /** 0 = cartão em destaque, no topo da pilha */
  stackPosition: number
  totalCards: number
  motionAllowed: boolean
  onPick: (t: EmptyStateTopic) => void
}

export function StackingTopicCard({
  topic,
  stackPosition,
  totalCards,
  motionAllowed,
  onPick,
}: StackingTopicCardProps) {
  const d = stackPosition
  const n = Math.max(1, totalCards)
  const dVis = Math.min(d, MAX_VISUAL_DEPTH)

  const scale = motionAllowed
    ? Math.max(0.88, 1 - dVis * 0.042)
    : 1
  const opacity = motionAllowed
    ? Math.max(0.74, 1 - dVis * 0.055)
    : 1
  const rotateX = motionAllowed ? dVis * ROTATE_X_PER_STEP : 0
  const y = motionAllowed ? dVis * Y_PER_STEP_PX : 0
  const z = motionAllowed ? dVis * Z_PER_STEP_PX : 0
  const zIndex = n + 40 - d

  return (
    <motion.div
      className="stacking-card-outer"
      initial={false}
      animate={{
        scale,
        opacity,
        rotateX,
        y,
        z,
        zIndex,
      }}
      transition={{
        duration: 1.45,
        ease: [0.45, 0.05, 0.25, 1],
      }}
      style={{
        transformStyle: 'preserve-3d',
        transformOrigin: '50% 35%',
      }}
    >
      <motion.button
        type="button"
        className="stacking-card-face w-full"
        onClick={() => onPick(topic)}
        whileTap={{ scale: motionAllowed ? 0.99 : 1 }}
      >
        <span className="stacking-card-icon" aria-hidden>
          {topic.icon}
        </span>
        <div className="stacking-card-text-block">
          <h3 className="stacking-card-title">{topic.title}</h3>
          <p className="stacking-card-desc">{topicCardPreview(topic.text)}</p>
        </div>
      </motion.button>
    </motion.div>
  )
}
