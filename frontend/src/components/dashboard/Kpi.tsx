import type { ReactNode } from 'react'

export function Kpi({ title, icon, children, className = '' }: { title: string; icon: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={`glass lift flex min-h-[214px] flex-col rounded-[28px] p-5 ${className}`}>
      <div className="mb-3 flex items-start justify-between">
        <span className="text-sm font-semibold text-ink-700">{title}</span>
        <span className="grid size-8 place-items-center rounded-full bg-brand-50 text-brand-600">{icon}</span>
      </div>
      {children}
    </div>
  )
}
