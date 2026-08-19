/** Progress through the calibration flow: which step is done, current, pending. */
export default function StepIndicator({
  labels,
  current,
}: {
  labels: string[];
  current: number;
}) {
  return (
    <ol className="flex flex-wrap gap-x-4 gap-y-1 text-2xs">
      {labels.map((label, i) => (
        <li
          key={label}
          aria-current={i === current ? "step" : undefined}
          className={
            i < current
              ? "font-semibold text-emerald-600"
              : i === current
                ? "font-semibold text-primary-800"
                : "text-slate-400"
          }
        >
          <span className="tabular-nums">{i + 1}</span> {label}
        </li>
      ))}
    </ol>
  );
}
