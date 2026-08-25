import Link from "next/link";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-4xl flex-col items-center justify-center gap-6 px-6 text-center">
      <span className="rounded-full bg-teal-100 px-3 py-1 text-xs font-medium text-teal-800">
        Pre-construction planning assistant
      </span>
      <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">
        See your house renovated — before you spend a rupee.
      </h1>
      <p className="max-w-2xl text-lg text-zinc-600">
        Upload a photo of your exterior, pick materials for walls, railings and pillars, preview a realistic
        redesign, and get a transparent quantity and cost estimate you can discuss with your contractor.
      </p>
      <div className="flex gap-3">
        <Link href="/register" className="rounded-md bg-teal-700 px-5 py-2.5 text-white hover:bg-teal-800">
          Get started
        </Link>
        <Link href="/login" className="rounded-md border px-5 py-2.5 hover:bg-white">
          Sign in
        </Link>
      </div>
    </main>
  );
}
