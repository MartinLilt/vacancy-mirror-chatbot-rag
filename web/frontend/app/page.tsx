import Link from "next/link";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-gray-950 text-white">
      {/* Hero */}
      <section className="flex flex-col items-center justify-center px-6 py-36 text-center">
        <div className="inline-flex items-center gap-2 bg-indigo-950 border border-indigo-800 text-indigo-300 text-xs font-medium px-4 py-1.5 rounded-full mb-8 tracking-wide uppercase">
          ✦ AI-powered job matching
        </div>
        <h1 className="text-6xl md:text-7xl font-semibold tracking-[-0.03em] leading-[1.08] mb-6 max-w-3xl">
          Find the right jobs on Upwork —{" "}
          <span className="bg-gradient-to-r from-indigo-400 via-violet-400 to-purple-400 bg-clip-text text-transparent">
            automatically
          </span>
        </h1>
        <p className="text-lg text-gray-400 max-w-lg mb-10 leading-relaxed">
          Vacancy Mirror scans Upwork daily and sends you only the jobs that
          match your skills. No noise. No manual browsing.
        </p>
        <Link
          href="https://t.me/VacancyMirrorBot"
          className="bg-indigo-600 hover:bg-indigo-500 text-white font-semibold px-8 py-4 rounded-xl text-lg transition"
        >
          Start in Telegram →
        </Link>
      </section>

      {/* Features */}
      <section className="max-w-4xl mx-auto px-6 pt-20 pb-4 grid grid-cols-1 md:grid-cols-3 gap-8">
        {[
          {
            icon: "📊",
            title: "Weekly Trends Report",
            desc: "See which skills and roles are growing across all 12 Upwork categories — every week, for free.",
          },
          {
            icon: "�",
            title: "AI Market Assistant",
            desc: "Ask anything about the freelance market. Get a career roadmap, niche advice, and proposal tips.",
          },
          {
            icon: "🎯",
            title: "Profile & Portfolio Agent",
            desc: "Get personalised recommendations to improve your profile title, skills, and portfolio projects.",
          },
        ].map((f) => (
          <div key={f.title} className="bg-gray-900 rounded-2xl p-6">
            <div className="text-4xl mb-4">{f.icon}</div>
            <h3 className="text-xl font-semibold mb-2">{f.title}</h3>
            <p className="text-gray-400 text-sm">{f.desc}</p>
          </div>
        ))}
      </section>
      <div className="text-center py-6">
        <Link href="/benefits" className="text-indigo-400 text-sm hover:underline">
          See all 7 features →
        </Link>
      </div>

      {/* Pricing */}
      <section className="max-w-3xl mx-auto px-6 py-20 text-center">
        <h2 className="text-3xl font-bold mb-4">Pricing</h2>
        <p className="text-gray-400 mb-12">
          Start free.{" "}
          <Link href="/pricing" className="text-indigo-400 hover:underline">
            See all plans →
          </Link>
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="bg-gray-900 rounded-2xl p-8 border border-gray-800 text-left">
            <h3 className="text-xl font-bold mb-2">Plus</h3>
            <p className="text-4xl font-bold mb-4">
              $9.99<span className="text-lg text-gray-400">/mo</span>
            </p>
            <ul className="text-gray-400 text-sm space-y-2 mb-8">
              <li>✓ 60 AI messages / day</li>
              <li>✓ Profile Optimisation Expert</li>
              <li>✓ Weekly Profile &amp; Projects Agent</li>
              <li>✓ Up to 5 portfolio projects reviewed</li>
            </ul>
            <a
              href={process.env.NEXT_PUBLIC_STRIPE_PLUS_URL ?? "#"}
              className="block bg-indigo-600 hover:bg-indigo-500 text-white font-semibold py-3 rounded-xl transition text-center"
            >
              Get Plus
            </a>
          </div>
          <div className="bg-indigo-950/60 rounded-2xl p-8 border border-indigo-500/60 text-left">
            <h3 className="text-xl font-bold mb-2">Pro Plus</h3>
            <p className="text-4xl font-bold mb-4">
              $19.99<span className="text-lg text-indigo-300">/mo</span>
            </p>
            <ul className="text-indigo-200 text-sm space-y-2 mb-8">
              <li>✓ 120 AI messages / day</li>
              <li>✓ Extended Projects Agent</li>
              <li>✓ Up to 12 portfolio projects reviewed</li>
              <li>✓ Weekly Skills &amp; Tags Report</li>
            </ul>
            <a
              href={process.env.NEXT_PUBLIC_STRIPE_PRO_PLUS_URL ?? "#"}
              className="block bg-white text-indigo-900 font-semibold py-3 rounded-xl transition hover:bg-indigo-100 text-center"
            >
              Get Pro Plus
            </a>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-gray-800 text-center text-gray-600 text-sm py-8 space-x-4">
        <span>© {new Date().getFullYear()} Vacancy Mirror</span>
        <Link href="/benefits" className="hover:text-gray-400">
          Features
        </Link>
        <Link href="/pricing" className="hover:text-gray-400">
          Pricing
        </Link>
        <Link href="/privacy" className="hover:text-gray-400">
          Privacy Policy
        </Link>
        <a href="mailto:support@vacancy-mirror.com" className="hover:text-gray-400">
          Contact
        </a>
      </footer>
    </main>
  );
}
