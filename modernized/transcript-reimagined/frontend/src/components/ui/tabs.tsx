import * as React from "react"
import * as TabsPrimitive from "@radix-ui/react-tabs"
import { cn } from "@/lib/utils"

const Tabs = TabsPrimitive.Root

const TabsList = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.List>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.List>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.List
    ref={ref}
    className={cn(
      "relative inline-flex h-10 items-center justify-center rounded-full bg-canvas-soft p-1 text-mute",
      className
    )}
    {...props}
  />
))
TabsList.displayName = TabsPrimitive.List.displayName

const TabsTrigger = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Trigger
    ref={ref}
    className={cn(
      "inline-flex items-center justify-center whitespace-nowrap rounded-sm px-3 py-1.5 text-sm font-normal ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 data-[state=active]:bg-canvas data-[state=active]:text-foreground",
      className
    )}
    {...props}
  />
))
TabsTrigger.displayName = TabsPrimitive.Trigger.displayName

const TabsContent = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Content>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Content
    ref={ref}
    className={cn(
      "mt-2 ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
      className
    )}
    {...props}
  />
))
TabsContent.displayName = TabsPrimitive.Content.displayName

/**
 * 一组标签共用的一条下划线：切换是「这条线滑过去」，不是两条线各自淡入淡出
 * ——后者读起来是一个消失、一个出现。
 *
 * 只动 transform；宽度用 scaleX 拉（2px 直角线不会变形），不必动 width 触发 layout。
 * 首次落位、窗口与字体变化不做动画，否则一进页面就自己横滑一次。
 */
function TabUnderline({
  listRef,
  value,
}: {
  listRef: React.RefObject<HTMLElement | null>
  value: string
}) {
  const barRef = React.useRef<HTMLSpanElement>(null)
  const placed = React.useRef(false)

  const place = React.useCallback(
    (animate: boolean) => {
      const list = listRef.current
      const bar = barRef.current
      const active = list?.querySelector<HTMLElement>('[data-state="active"]')
      if (!list || !bar || !active) return
      if (!animate) bar.style.transition = 'none'
      const listBox = list.getBoundingClientRect()
      const activeBox = active.getBoundingClientRect()
      bar.style.transform = `translateX(${activeBox.left - listBox.left}px) scaleX(${activeBox.width})`
      if (!animate) {
        // 逼一次样式落盘再把过渡还回去：否则这次瞬移会被并进下一帧，看着还是滑过去的
        void bar.offsetWidth
        bar.style.transition = ''
      }
      placed.current = true
    },
    [listRef],
  )

  React.useLayoutEffect(() => {
    place(placed.current)
  }, [value, place])

  React.useEffect(() => {
    const list = listRef.current
    if (!list) return
    const observer = new ResizeObserver(() => place(false))
    observer.observe(list)
    return () => observer.disconnect()
  }, [listRef, place])

  return <span ref={barRef} aria-hidden="true" className="tab-underline" />
}

export { Tabs, TabsList, TabsTrigger, TabsContent, TabUnderline }
