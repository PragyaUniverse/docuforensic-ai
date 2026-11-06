import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md font-medium transition-[color,background-color,border-color,transform] duration-150 active:translate-y-px disabled:pointer-events-none disabled:opacity-45 cursor-pointer [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary: "bg-accent text-white hover:bg-accent-dark",
        secondary: "border border-line-strong bg-panel text-ink hover:bg-hover",
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
