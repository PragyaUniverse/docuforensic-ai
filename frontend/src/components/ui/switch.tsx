import * as S from "@radix-ui/react-switch";
import { cn } from "@/lib/utils";

export function Switch({
  checked,
  onCheckedChange,
  label,
  className,
}: {
  checked: boolean;
  onCheckedChange: (v: boolean) => void;
  label: string;
  className?: string;
}) {
  return (
    <S.Root
      checked={checked}
      onCheckedChange={onCheckedChange}
      aria-label={label}
      className={cn(
        "relative h-4 w-7 shrink-0 cursor-pointer rounded-full border border-line-strong bg-raised data-[state=checked]:border-ink data-[state=checked]:bg-ink",
        className,
      )}
    >
      <S.Thumb className="block size-2.5 translate-x-0.5 rounded-full bg-ink-2 transition-transform data-[state=checked]:translate-x-[14px] data-[state=checked]:bg-ground" />
    </S.Root>
  );
}
