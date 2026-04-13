import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Page Not Found",
  robots: { index: false, follow: false },
};

export default function NotFound() {
  return (
    <main className="min-h-screen bg-gray-950 text-white flex items-center justify-center px-6">
      <div className="text-center max-w-md">
        <div className="text-6xl mb-6">🔍</div>
        <h1 className="text-4xl font-semibold tracking-tight mb-3">
          Page not found
        </h1>
        <p className="text-gray-400 mb-10">
          The page you&apos;re looking for doesn&apos;t exist or has been moved.
        </p>
        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <Link
            href="/"
            className="bg-indigo-600 hover:bg-indigo-500 text-white font-semibold px-8 py-3 rounded-xl text-sm transition-colors"
          >
            ← Back to home
          </Link>
          <Link
            href="/benefits"
            className="bg-white/10 hover:bg-white/20 text-white font-semibold px-8 py-3 rounded-xl text-sm transition-colors"
          >
            See all features
          </Link>
        </div>
      </div>
    </main>
  );
}

