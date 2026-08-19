import Link from "next/link";
import { ChevronRight } from "lucide-react";
import CalibratePicker from "@/components/CalibratePicker";

interface Props {
  params: { id: string };
}

export const metadata = { title: "Calibrate camera" };

export default function CalibratePage({ params }: Props) {
  return (
    <main id="main-content" className="mx-auto max-w-3xl space-y-5">
      <nav
        aria-label="Breadcrumb"
        className="flex items-center gap-1.5 text-xs text-slate-400"
      >
        <Link href="/" className="transition-colors hover:text-slate-700">
          Matches
        </Link>
        <ChevronRight className="h-3 w-3" aria-hidden="true" />
        <Link
          href={`/matches/${params.id}`}
          className="transition-colors hover:text-slate-700"
        >
          Match
        </Link>
        <ChevronRight className="h-3 w-3" aria-hidden="true" />
        <span className="font-medium text-slate-700">Calibrate camera</span>
      </nav>

      <div>
        <h1 className="text-xl font-bold text-slate-900">Calibrate camera</h1>
        <p className="mt-0.5 max-w-2xl text-sm text-slate-500">
          Marking the four pitch corners lets the analysis work in metres
          instead of pixels, which is what makes formations and distances real.
          The camera framing is fixed, so a still from any match at this ground
          works.
        </p>
      </div>

      <CalibratePicker matchId={params.id} />
    </main>
  );
}
