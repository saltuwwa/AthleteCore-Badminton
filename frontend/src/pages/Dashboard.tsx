import { motion } from 'framer-motion'
import { ChatArea } from '../components/chat/ChatArea'
import { InputBar } from '../components/chat/InputBar'
import { MetricsRow } from '../components/metrics/MetricsRow'
import { useChat } from '../hooks/useChat'

export const Dashboard = () => {
  const { messages, send, isSending } = useChat()

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ staggerChildren: 0.05 }}
      className="flex h-full flex-col gap-3 p-4"
    >
      <MetricsRow />
      <ChatArea messages={messages} />
      <InputBar onSend={send} isSending={isSending} />
    </motion.div>
  )
}
