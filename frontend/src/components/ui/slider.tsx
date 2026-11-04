import * as S from "@radix-ui/react-slider";

export function Slider({
  value,
  onChange,
  label,
  min = 0,
  max = 100,
}: {
  value: number;
  onChange: (v: number) => void;
  label: string;
  min?: number;
  max?: number;
}) {
  return (
    <S.Root
      className="relative flex h-4 w-24 touch-none select-none items-center"
      value={[value]}
      min={min}
      max={max}
      onValueChange={(v) => onChange(v[0])}
    >
      <S.Track className="relative h-[3px] grow rounded-full bg-line-strong">
        <S.Range className="absolute h-full rounded-full bg-ink-2" />
      </S.Track>
      <S.Thumb aria-label={label} className="block size-3 rounded-full border border-ground bg-ink" />
    </S.Root>
  );
}
