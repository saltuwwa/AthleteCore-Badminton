import { motion } from 'framer-motion'
import { MetricCard } from './MetricCard'

export const MetricsRow = () => {
  return (
    <div className="grid grid-cols-3 gap-3">
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }}>
        <MetricCard label="PERFORMANCE SCORE" value="8.4" delta="+0.6 vs last week" tone="accent" />
      </motion.div>
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2, delay: 0.05 }}>
        <MetricCard label="ERRORS DETECTED" value="5" delta="-2 trend improving" tone="warn" />
      </motion.div>
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2, delay: 0.1 }}>
        <MetricCard label="RECOVERY LOAD" value="62%" delta="+4% this microcycle" tone="amber" />
      </motion.div>
    </div>
  )
}
