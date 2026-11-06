import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-lg font-medium transition-[color,background-color,border-color,transform] duration-150 active:translate-y-px disabled:pointer-events-none disabled:opacity-45 cursor-pointer [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary: "bg-accent text-[#03141a] shadow-[0_0_0_1px_rgba(var(--color-glow),0.5),0_8px_28px_-10px_rgba(var(--color-glow),0.8)] hover:brightness-110 hover:shadow-[0_0_0_1px_rgba(var(--color-glow),0.7),0_10px_34px_-8px_rgba(var(--color-glow),0.95)] active:translate-y-px",
        secondary: "border border-line-strong bg-[color-mix(in_srgb,var(--color-ink)_3%,transparent)] text-ink hover:border-[rgba(var(--color-glow),0.45)] hover:bg-hover active:translate-y-px",
        ghost: "text-ink-2 hover:bg-hover hover:text-ink",
        danger: "border border-man text-man hover:bg-man-dim",
      },
      size: {
        sm: "h-8 px-2.5 text-[14px]",
        md: "h-10 px-4 text-[15px]",
        lg: "h-11 px-5 text-[15px]",
        icon: "size-8",
      },
    },
    defaultVariants: { variant: "secondary", size: "md" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return <Comp ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...props} />;
  },
);
Button.displayName = "Button";
