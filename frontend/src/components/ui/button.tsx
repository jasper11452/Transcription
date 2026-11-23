import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

// DESIGN.md：按钮一律胶囊形（rounded.pill）、400 字重、无投影；
// 白色实心是唯一例外（主 CTA），其余为描边胶囊。
const buttonVariants = cva(
  // 按下时轻微缩小：160ms ease-out 给即时反馈，不拖慢高频操作。
  "inline-flex items-center justify-center whitespace-nowrap rounded-full text-sm font-normal transition-[color,background-color,border-color,transform] duration-150 ease-out active:scale-[0.97] motion-reduce:active:scale-100 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground hover:bg-ink-hover",
        destructive:
          "border border-hairline bg-transparent text-destructive hover:bg-destructive/10",
        outline:
          "border border-hairline bg-canvas text-foreground hover:bg-canvas-soft",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-canvas-mid/40",
        ghost: "text-body hover:bg-canvas-soft hover:text-foreground",
        link: "text-foreground underline-offset-4 hover:underline",
      },
      size: {
        default: "h-9 px-5",
        sm: "h-8 px-4 text-[13px]",
        lg: "h-11 px-8",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }
