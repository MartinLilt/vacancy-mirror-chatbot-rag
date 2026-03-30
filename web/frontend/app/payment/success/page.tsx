"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

const BOT_URL = "https://t.me/VacancyMirrorBot";

function SuccessContent() {
  const params = useSearchParams();
  // Stripe can pass ?session_id=... — we acknowledge but don't display it
  const hasSession = Boolean(params.get("session_id"));

  return (
    <div className="flex flex-col items-center text-center">
      {/* Animated checkmark */}
      <div className="w-20 h-20 rounded-full bg-indigo-600/20 border border-indigo-500/40 flex items-center justify-center mb-8">
        <svg
          className="w-9 h-9 text-indigo-400"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2.5}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M5 13l4 4L19 7"
          />
        </svg>
      </div>

      <h1 className="text-3xl font-semibold tracking-tight mb-3">
        Payment successful!
      </h1>
      <p className="text-gray-400 text-lg mb-2">
        Your subscription is now active.
      </p>

      {hasSession && (
        <p className="text-gray-600 text-xs mb-2">
          Your receipt will arrive by email shortly.
        </p>
      )}

      <p className="text-gray-400 mb-10 max-w-sm">
        Head back to the Telegram bot — your upgraded plan is ready to use
        right away.
      </p>

      <a
        href={BOT_URL}
        target="_blank"
        rel="noopener noreferrer"
        className="bg-indigo-600 hover:bg-indigo-500 transition-colors text-white font-semibold px-8 py-3 rounded-xl text-sm"
      >
        Open Vacancy Mirror in Telegram
      </a>

      <a href="/" className="mt-6 text-indigo-400 text-sm hover:underline">
        ← Back to home
      </a>
    </div>
  );
}

export default function PaymentSuccessPage() {
  return (
    <main className="min-h-screen bg-gray-950 text-white flex items-center justify-center px-6">
      <Suspense>
        <SuccessContent />
      </Suspense>
    </main>
  );
}
