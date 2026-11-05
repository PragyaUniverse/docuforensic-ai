import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-full font-semibold transition-[color,background-color,border-color,transform,box-shadow] duration-150 disabled:pointer-events-none disabled:opacity-45 [&_svg]:size-4 [&_svg]:shrink-0 cursor-pointer",
  {
    variants: {
      variant: {
        primary: "border-2 border-[var(--color-edge)] bg-accent text-white shadow-[3px_3px_0_var(--color-edge)] hover:-translate-y-px hover:shadow-[4px_4px_0_var(--color-edge)] active:translate-x-[3px] active:translate-y-[3px] active:shadow-none",
        secondary: "border-2 border-[var(--color-edge)] bg-panel text-ink shadow-[3px_3px_0_var(--color-edge)] hover:-translate-y-px hover:bg-raised hover:shadow-[4px_4px_0_var(--color-edge)] active:translate-x-[3px] active:translate-y-[3px] active:shadow-none",
        ghost: "text-ink-2 hover:bg-hover hover:text-ink",
        danger: "border-2 border-man bg-man-dim text-man shadow-[3px_3px_0_var(--color-man)] active:translate-x-[3px] active:translate-y-[3px] active:shadow-none",
      },
      size: {
        sm: "h-8 px-3.5 text-[14px]",
        md: "h-11 px-5 text-[15px]",
        lg: "h-12 px-7 text-[16px]",
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
