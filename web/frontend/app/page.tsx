import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Vacancy Mirror — AI market intelligence for Upwork freelancers",
  description:
    "Vacancy Mirror analyses the Upwork job market and gives you " +
    "weekly trend reports, AI-powered profile advice, and smart " +
    "portfolio recommendations — all inside Telegram.",
  alternates: { canonical: "https://vacancy-mirror.com" },
  openGraph: { url: "https://vacancy-mirror.com" },
};

const features = [
  {
    icon: "📊",
    title: "Weekly Trends Report",
    desc: "See which skills and roles are growing across all 12 Upwork categories — every week, for free.",
  },
  {
    icon: "💬",
    title: "AI Market Assistant",
    desc: "Ask anything about the freelance market. Career roadmap, niche comparisons, proposal tips.",
  },
  {
    icon: "🎯",
    title: "Profile & Portfolio Agent",
    desc: "Personalised recommendations to improve your title, skills, and portfolio projects.",
  },
];

const stats = [
  { value: "12", label: "Upwork categories tracked" },
  { value: "7", label: "AI-powered tools" },
  { value: "Free", label: "to get started" },
];

export default function HomePage() {
  return (
    <main className="min-h-screen bg-gray-950 text-white">
      {/* Hero */}
      <section className="relative flex flex-col items-center justify-center px-6 py-32 text-center overflow-hidden">
        <div aria-hidden className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div className="w-[600px] h-[400px] rounded-full bg-indigo-600/10 blur-[120px]" />
        </div>

        <div className="relative z-10 flex flex-col items-center">
          <div className="inline-flex items-center gap-2 bg-indigo-950 border border-indigo-800/60 text-indigo-300 text-xs font-medium px-4 py-1.5 rounded-full mb-8 tracking-wide">
            ✦ AI-powered freelance market intelligence
          </div>

          <h1 className="text-5xl md:text-7xl font-semibold tracking-[-0.03em] leading-[1.08] mb-6 max-w-3xl text-balance">
            Understand the Upwork market —{" "}
            <span className="bg-gradient-to-r from-indigo-400 via-violet-400 to-purple-400 bg-clip-text text-transparent">
              automatically
            </span>
          </h1>

          <p className="text-lg text-gray-400 max-w-xl mb-10 leading-relaxed">
            Weekly trends, AI profile advice, and portfolio recommendations
            for freelancers — delivered inside Telegram. No dashboards, no noise.
          </p>

          <div className="flex flex-col sm:flex-row gap-3 items-center">
            <a
              href="https://t.me/VacancyMirrorBot"
              target="_blank"
              rel="noopener noreferrer"
              className="bg-indigo-600 hover:bg-indigo-500 text-white font-semibold px-8 py-3.5 rounded-xl text-base transition-colors shadow-lg shadow-indigo-600/20"
            >
              Start free in Telegram →
            </a>
            <Link
              href="/benefits"
              className="text-gray-400 hover:text-white text-sm transition-colors px-4 py-3.5"
            >
              See all features
            </Link>
          </div>
        </div>
      </section>

      {/* Stats */}
      <section className="border-y border-white/5 bg-white/[0.02]">
        <div className="max-w-3xl mx-auto px-6 py-10 grid grid-cols-3 gap-6 text-center">
          {stats.map((s) => (
            <div key={s.label}>
              <div className="text-3xl font-bold text-white mb-1">{s.value}</div>
              <div className="text-sm text-gray-500">{s.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Features */}
      <section className="max-w-5xl mx-auto px-6 py-24">
        <div className="text-center mb-14">
          <h2 className="text-3xl font-semibold tracking-tight mb-3">
            Everything you need to grow on Upwork
          </h2>
          <p className="text-gray-400 max-w-lg mx-auto">
            From weekly market reports to personalised AI coaching — without leaving Telegram.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          {features.map((f) => (
            <div
              key={f.title}
              className="bg-white/5 border border-white/10 rounded-2xl p-7 hover:border-indigo-500/30 transition-colors"
            >
              <div className="text-3xl mb-4">{f.icon}</div>
              <h3 className="text-lg font-semibold mb-2">{f.title}</h3>
              <p className="text-gray-400 text-sm leading-relaxed">{f.desc}</p>
            </div>
          ))}
        </div>

        <div className="text-center">
          <Link href="/benefits" className="text-indigo-400 text-sm hover:underline">
            See all 7 features →
          </Link>
        </div>
      </section>

      {/* Pricing preview */}
      <section className="max-w-5xl mx-auto px-6 pb-24">
        <div className="text-center mb-14">
          <h2 className="text-3xl font-semibold tracking-tight mb-3">
            Simple, transparent pricing
          </h2>
          <p className="text-gray-400">
            Start free.{" "}
            <Link href="/pricing" className="text-indigo-400 hover:underline">
              Compare all plans →
            </Link>
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Free */}
          <div className="bg-white/5 border border-white/10 rounded-2xl p-7 flex flex-col">
            <div className="mb-6">
              <h3 className="text-lg font-semibold mb-1">Free</h3>
              <div className="text-4xl font-bold mb-3">$0</div>
              <p className="text-gray-400 text-sm">Forever. No card required.</p>
            </div>
            <ul className="space-y-2 text-sm text-gray-300 mb-8 flex-1">
              <li className="flex gap-2"><span className="text-indigo-400">✓</span>35 AI messages / day</li>
              <li className="flex gap-2"><span className="text-indigo-400">✓</span>Weekly Trends Report</li>
              <li className="flex gap-2"><span className="text-indigo-400">✓</span>Weekly Trend Charts</li>
            </ul>
            <a
              href="https://t.me/VacancyMirrorBot"
              target="_blank"
              rel="noopener noreferrer"
              className="block text-center bg-white/10 hover:bg-white/20 text-white font-semibold py-3 rounded-xl transition-colors text-sm"
            >
              Start free
            </a>
          </div>

          {/* Plus */}
          <div className="relative bg-indigo-950/50 border border-indigo-500/50 rounded-2xl p-7 flex flex-col shadow-[0_0_40px_-10px_rgba(99,102,241,0.35)]">
            <div className="absolute -top-3 left-1/2 -translate-x-1/2">
              <span className="bg-indigo-600 text-white text-xs font-semibold px-3 py-1 rounded-full">
                Most popular
              </span>
            </div>
            <div className="mb-6">
              <h3 className="text-lg font-semibold mb-1">Plus</h3>
              <div className="text-4xl font-bold mb-3">
                $9.99<span className="text-lg text-gray-400 font-normal">/mo</span>
              </div>
              <p className="text-gray-400 text-sm">Profile & portfolio growth.</p>
            </div>
            <ul className="space-y-2 text-sm text-gray-300 mb-8 flex-1">
              <li className="flex gap-2"><span className="text-indigo-400">✓</span>60 AI messages / day</li>
              <li className="flex gap-2"><span className="text-indigo-400">✓</span>Profile Optimisation Expert</li>
              <li className="flex gap-2"><span className="text-indigo-400">✓</span>Weekly Profile &amp; Projects Agent</li>
              <li className="flex gap-2"><span className="text-indigo-400">✓</span>Up to 5 portfolio projects</li>
            </ul>
            <a
              href={process.env.NEXT_PUBLIC_STRIPE_PLUS_URL ?? "#"}
              target="_blank"
              rel="noopener noreferrer"
              className="block text-center bg-indigo-600 hover:bg-indigo-500 text-white font-semibold py-3 rounded-xl transition-colors text-sm"
            >
              Get Plus — $9.99 / mo
            </a>
          </div>

          {/* Pro Plus */}
          <div className="bg-white/5 border border-white/10 rounded-2xl p-7 flex flex-col">
            <div className="mb-6">
              <h3 className="text-lg font-semibold mb-1">Pro Plus</h3>
              <div className="text-4xl font-bold mb-3">
                $19.99<span className="text-lg text-gray-400 font-normal">/mo</span>
              </div>
              <p className="text-gray-400 text-sm">Full portfolio coverage.</p>
            </div>
            <ul className="space-y-2 text-sm text-gray-300 mb-8 flex-1">
              <li className="flex gap-2"><span className="text-indigo-400">✓</span>120 AI messages / day</li>
              <li className="flex gap-2"><span className="text-indigo-400">✓</span>Extended Projects Agent</li>
              <li className="flex gap-2"><span className="text-indigo-400">✓</span>Up to 12 portfolio projects</li>
              <li className="flex gap-2"><span className="text-indigo-400">✓</span>Weekly Skills &amp; Tags Report</li>
            </ul>
            <a
              href={process.env.NEXT_PUBLIC_STRIPE_PRO_PLUS_URL ?? "#"}
              target="_blank"
              rel="noopener noreferrer"
              className="block text-center bg-white/10 hover:bg-white/20 text-white font-semibold py-3 rounded-xl transition-colors text-sm"
            >
              Get Pro Plus — $19.99 / mo
            </a>
          </div>
        </div>
      </section>

      {/* CTA banner */}
      <section className="max-w-5xl mx-auto px-6 pb-24">
        <div className="relative overflow-hidden bg-indigo-600 rounded-3xl px-10 py-16 text-center">
          <div aria-hidden className="pointer-events-none absolute inset-0">
            <div className="absolute -top-20 -right-20 w-64 h-64 rounded-full bg-white/10 blur-3xl" />
            <div className="absolute -bottom-20 -left-20 w-64 h-64 rounded-full bg-violet-600/40 blur-3xl" />
          </div>
          <div className="relative z-10">
            <h2 className="text-3xl font-semibold mb-3">Ready to grow on Upwork?</h2>
            <p className="text-indigo-100 mb-8 max-w-md mx-auto">
              Start with the free plan today. No registration, no email —
              just open the bot in Telegram.
            </p>
            <a
              href="https://t.me/VacancyMirrorBot"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-block bg-white text-indigo-700 font-semibold px-8 py-3.5 rounded-xl hover:bg-indigo-50 transition-colors text-base shadow-lg"
            >
              Open Vacancy Mirror →
            </a>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/5 py-10">
        <div className="max-w-5xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-4 text-sm text-gray-600">
          <div className="flex items-center gap-2">
            <span className="text-indigo-500">◈</span>
            <span>© {new Date().getFullYear()} Vacancy Mirror</span>
          </div>
          <nav className="flex items-center gap-6">
            <Link href="/benefits" className="hover:text-gray-400 transition-colors">Features</Link>
            <Link href="/pricing" className="hover:text-gray-400 transition-colors">Pricing</Link>
            <Link href="/privacy" className="hover:text-gray-400 transition-colors">Privacy</Link>
            <a href="mailto:support@vacancy-mirror.com" className="hover:text-gray-400 transition-colors">Contact</a>
          </nav>
        </div>
      </footer>
    </main>
  );
}
