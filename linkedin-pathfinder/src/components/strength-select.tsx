import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { STRENGTH_LABEL } from "@/lib/routes"
import type { Strength } from "@/lib/types"

export function StrengthSelect({ value, onChange, size = "default", className }: { value: Strength; onChange: (s: Strength) => void; size?: "sm" | "default"; className?: string }) {
  return (
    <Select value={String(value)} onValueChange={(v) => onChange(Number(v) as Strength)}>
      <SelectTrigger size={size} className={className}>
        <SelectValue>{STRENGTH_LABEL[value]}</SelectValue>
      </SelectTrigger>
      <SelectContent>
        {([3, 2, 1] as Strength[]).map((s) => (
          <SelectItem key={s} value={String(s)}>
            {STRENGTH_LABEL[s]}
            <span className="text-muted-foreground text-xs">{s === 3 ? "would gladly intro" : s === 2 ? "know each other" : "barely know"}</span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
