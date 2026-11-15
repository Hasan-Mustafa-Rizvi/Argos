import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"
import { Slot } from "radix-ui"

const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center gap-2 rounded-none border-2 font-sans text-base font-bold whitespace-nowrap transition-colors select-none disabled:pointer-events-none disabled:opacity-60 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-5",
  {
    variants: {
      variant: {
        default:
          "border-primary bg-primary text-primary-foreground hover:bg-[color-mix(in_oklab,var(--primary)_86%,var(--paper))]",
        secondary: "border-primary bg-background text-primary hover:bg-wash",
        ghost: "border-transparent bg-transparent text-primary hover:bg-wash",
        link: "border-transparent bg-transparent px-0 text-primary underline underline-offset-4 hover:no-underline",
      },
      size: {
        default: "min-h-11 px-5 py-2",
        sm: "min-h-9 px-3 py-1 text-sm",
        icon: "size-11",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }) {
  const Comp = asChild ? Slot.Root : "button"

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
