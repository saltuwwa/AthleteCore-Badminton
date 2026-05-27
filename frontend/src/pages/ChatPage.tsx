import { motion } from 'framer-motion'
import { ChatArea } from '../components/chat/ChatArea'
import { ChatInput } from '../components/chat/ChatInput'
import { PageTabs } from '../components/layout/PageTabs'
import { useChat } from '../hooks/useChat'

export const ChatPage = () => {
  const { messages, send, showVoiceDraft, isSending, needsMemory, addAiMessage } = useChat()

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="flex h-full flex-col overflow-hidden bg-[var(--bg-deep)]"
    >
      <header className="shrink-0 border-b border-[var(--border)] px-8 py-4">
        <div className="mx-auto flex max-w-3xl items-start justify-between gap-4">
          <div>
            <p className="label-mono">AI ASSISTANT</p>
            <h1 className="font-display mt-1 text-[22px] tracking-tight">
              Athlete<span className="text-[var(--accent)]">Core</span>
            </h1>
          </div>
          <PageTabs />
        </div>
      </header>

      <div className="thin-scrollbar min-h-0 flex-1 overflow-y-auto px-8 py-6">
        <div className="mx-auto flex min-h-full max-w-3xl flex-col">
          <ChatArea
            messages={messages}
            className="min-h-[200px] flex-1 border-0 bg-transparent p-0"
          />
        </div>
      </div>

      <footer className="shrink-0 border-t border-[var(--border)] px-8 py-5 backdrop-blur-md">
        <div className="mx-auto max-w-3xl">
          <ChatInput
            onSend={send}
            onVoiceTranscript={showVoiceDraft}
            onDocumentResult={addAiMessage}
            isSending={isSending}
            needsMemory={needsMemory}
            autoSendAfterVoice={false}
          />
        </div>
      </footer>
    </motion.div>
  )
}
