import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

// DESIGN.md：徽标不做彩色底，靠发丝线 + 灰阶文字；400 字重
const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-normal transition-colors focus:outline-none",
  {
    variants: {
      variant: {
        default: "border-hairline bg-canvas-soft text-body",
        secondary: "border-transparent bg-secondary text-secondary-foreground",
        destructive: "border-destructive/40 text-destructive",
        outline: "border-hairline text-body",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  )
}

export { Badge, badgeVariants }
