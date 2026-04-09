import type { CSSProperties } from 'react'
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useReducedMotion } from 'framer-motion'
import { EmptyStateTopicCard } from './EmptyStateTopicCard'
import type { EmptyStateTopic } from './emptyStateTopics'
import { topicCardPreview } from './emptyStateTopics'

/**
 * Duração de uma passagem completa por todas as páginas (loop linear).
 * Valores maiores = deslocamento mais lento.
 */
const MARQUEE_LOOP_SECONDS = 48

/** 4 colunas × 2 linhas — alinhado a `.carousel-grid-page`. */
const CARDS_PER_PAGE = 8

type EmptyStateTopicCarouselProps = {
  topics: EmptyStateTopic[]
  onPick: (t: EmptyStateTopic) => void
}

function chunkTopics<T>(items: T[], size: number): T[][] {
  if (size <= 0) return [items]
  const out: T[][] = []
  for (let i = 0; i < items.length; i += size) {
    out.push(items.slice(i, i + size))
  }
  return out.length ? out : [[]]
}

function CarouselGridCard({
  topic,
  onPick,
}: {
  topic: EmptyStateTopic
  onPick: (t: EmptyStateTopic) => void
}) {
  return (
    <button
      type="button"
      className="carousel-grid-card"
      onClick={() => onPick(topic)}
    >
      <span className="carousel-grid-card-icon-wrap" aria-hidden>
        <span className="carousel-grid-card-icon">{topic.icon}</span>
      </span>
      <span className="carousel-grid-card-title">{topic.title}</span>
      <p className="carousel-grid-card-desc">
        {topicCardPreview(topic.text, 150)}
      </p>
    </button>
  )
}

function MarqueePages({
  pages,
  onPick,
  suffix,
}: {
  pages: EmptyStateTopic[][]
  onPick: (t: EmptyStateTopic) => void
  suffix: string
}) {
  return (
    <>
      {pages.map((pageTopics, pi) => (
        <div
          key={`${suffix}-${pi}`}
          className="carousel-marquee-page"
        >
          <div
            className={
              pageTopics.length <= 4
                ? 'carousel-grid-page carousel-grid-page--marquee carousel-grid-page--marquee-rows-1'
                : 'carousel-grid-page carousel-grid-page--marquee carousel-grid-page--marquee-rows-2'
            }
          >
            {pageTopics.map((topic) => (
              <CarouselGridCard
                key={`${suffix}-${pi}-${topic.id}`}
                topic={topic}
                onPick={onPick}
              />
            ))}
          </div>
        </div>
      ))}
    </>
  )
}

export function EmptyStateTopicCarousel({
  topics,
  onPick,
}: EmptyStateTopicCarouselProps) {
  const reduceMotion = useReducedMotion()
  const clipRef = useRef<HTMLDivElement>(null)
  const [slideW, setSlideW] = useState(0)
  const [docHidden, setDocHidden] = useState(
    () => typeof document !== 'undefined' && document.hidden,
  )

  const pages = useMemo(
    () => chunkTopics(topics, CARDS_PER_PAGE),
    [topics],
  )
  const numPages = pages.length

  useLayoutEffect(() => {
    const el = clipRef.current
    if (!el) return
    const apply = () => {
      const cs = getComputedStyle(el)
      const pl = parseFloat(cs.paddingLeft) || 0
      const pr = parseFloat(cs.paddingRight) || 0
      setSlideW(Math.max(0, Math.round(el.clientWidth - pl - pr)))
    }
    apply()
    const ro = new ResizeObserver(apply)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  useEffect(() => {
    const onVis = () => setDocHidden(document.hidden)
    document.addEventListener('visibilitychange', onVis)
    return () => document.removeEventListener('visibilitychange', onVis)
  }, [])

  if (reduceMotion || topics.length === 0) {
    return (
      <div className="chat-topics-grid">
        {topics.map((topic) => (
          <EmptyStateTopicCard key={topic.id} topic={topic} onPick={onPick} />
        ))}
      </div>
    )
  }

  const clipStyle = {
    '--carousel-slide-w': `${slideW}px`,
    '--carousel-marquee-duration': `${MARQUEE_LOOP_SECONDS}s`,
  } as CSSProperties

  const singlePageView =
    numPages <= 1 ? (
      <div className="carousel-explorer-slide-clip" ref={clipRef} style={clipStyle}>
        <div className="carousel-marquee-page carousel-marquee-page--static">
          <div
            className={
              (pages[0]?.length ?? 0) <= 4
                ? 'carousel-grid-page carousel-grid-page--marquee carousel-grid-page--marquee-rows-1'
                : 'carousel-grid-page carousel-grid-page--marquee carousel-grid-page--marquee-rows-2'
            }
          >
            {(pages[0] ?? []).map((topic) => (
              <CarouselGridCard key={topic.id} topic={topic} onPick={onPick} />
            ))}
          </div>
        </div>
      </div>
    ) : (
      <div
        ref={clipRef}
        className={`carousel-explorer-slide-clip carousel-explorer-slide-clip--marquee${docHidden ? ' carousel-explorer-slide-clip--doc-hidden' : ''}`}
        style={clipStyle}
      >
        <div
          className={
            slideW > 0
              ? 'carousel-marquee-outer'
              : 'carousel-marquee-outer carousel-marquee-outer--idle'
          }
        >
          <div className="carousel-marquee-segment">
            <MarqueePages pages={pages} onPick={onPick} suffix="a" />
          </div>
          <div
            className="carousel-marquee-segment"
            aria-hidden
            inert
          >
            <MarqueePages pages={pages} onPick={onPick} suffix="b" />
          </div>
        </div>
      </div>
    )

  return (
    <div
      role="region"
      className="carousel-explorer"
      aria-roledescription="carrossel"
      aria-label="Sugestões em deslocamento contínuo — pausa ao passar o rato; toque num cartão para escolher"
    >
      <div className="carousel-explorer-panel">
        {singlePageView}
        <div className="carousel-explorer-footer carousel-explorer-footer--marquee">
          <p className="carousel-explorer-hint">
            Deslocamento contínuo — pausa ao pairar. Toque para selecionar uma
            categoria.
          </p>
        </div>
      </div>
    </div>
  )
}
