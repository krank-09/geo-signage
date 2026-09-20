import { createContext, ReactNode, useCallback, useContext, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { CheckCircle, Warning, X } from '@phosphor-icons/react'

interface Toast { id: number; tone: 'alert' | 'ok'; text: string }
const Ctx = createContext<(tone: Toast['tone'], text: string) => void>(() => {})
export const useToast = () => useContext(Ctx)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const push = useCallback((tone: Toast['tone'], text: string) => {
    const id = Date.now() + Math.random()
    setToasts((t) => [...t.slice(-3), { id, tone, text }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), tone === 'alert' ? 12000 : 5000)
  }, [])
  return (
    <Ctx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed bottom-5 right-5 z-[3000] flex w-[360px] max-w-[calc(100vw-2rem)] flex-col gap-2" role="status" aria-live="polite">
        <AnimatePresence initial={false}>
          {toasts.map((t) => (
            <motion.div key={t.id} layout initial={{ opacity: 0, x: 40, scale: 0.96 }} animate={{ opacity: 1, x: 0, scale: 1 }} exit={{ opacity: 0, x: 40 }}
              transition={{ type: 'spring', stiffness: 380, damping: 32 }}
              className={`pointer-events-auto flex items-start gap-3 rounded-2xl p-4 text-sm font-medium text-white shadow-2xl ${t.tone === 'alert' ? 'bg-red-600' : 'bg-emerald-600'}`}>
              {t.tone === 'alert' ? <Warning size={20} weight="fill" aria-hidden="true" className="mt-0.5 shrink-0" /> : <CheckCircle size={20} weight="fill" aria-hidden="true" className="mt-0.5 shrink-0" />}
              <span className="flex-1">{t.text}</span>
              <button onClick={() => setToasts((all) => all.filter((x) => x.id !== t.id))} aria-label="Dismiss" className="opacity-70 hover:opacity-100"><X size={16} aria-hidden="true" /></button>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </Ctx.Provider>
  )
}
