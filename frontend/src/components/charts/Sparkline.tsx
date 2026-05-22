type Props = {
  values: number[]
  color?: string
  fill?: string
  height?: number
}

export const Sparkline = ({ values, color = 'var(--accent)', fill = 'rgba(124,107,255,0.2)', height = 60 }: Props) => {
  if (values.length === 0) return null
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1
  const stepX = 100 / (values.length - 1 || 1)
  const points = values.map((v, i) => {
    const x = i * stepX
    const y = 100 - ((v - min) / range) * 100
    return `${x},${y}`
  })
  const path = `M${points[0]} L${points.slice(1).join(' ')}`
  const areaPath = `${path} L100,100 L0,100 Z`
  return (
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{ height, width: '100%' }}>
      <path d={areaPath} fill={fill} stroke="none" />
      <path d={path} fill="none" stroke={color} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
    </svg>
  )
}
