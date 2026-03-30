import Link from "next/link";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-gray-950 text-white">
      {/* Hero */}
      <section className="flex flex-col items-center justify-center px-6 py-32 text-center">
        <h1 className="text-5xl font-bold tracking-tight mb-6">
          Find the right jobs on Upwork —<br />
          <span className="text-indigo-400">automatically</span>
        </h1>
        <p className="text-lg text-gray-400 max-w-xl mb-10">
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
      <section className="max-w-4xl mx-auto px-6 py-20 grid grid-cols-1 md:grid-cols-3 gap-8">
        {[
          {
            icon: "🤖",
            title: "AI Matching",
            desc: "Semantic search finds jobs that match your profile, not just keywords.",
          },
          {
            icon: "📬",
            title: "Daily Digest",
            desc: "Get a curated list of fresh vacancies every morning via Telegram.",
          },
          {
            icon: "💳",
            title: "Simple Pricing",
            desc: "Free tier available. Upgrade for more categories and faster updates.",
          },
        ].map((f) => (
          <div key={f.title} className="bg-gray-900 rounded-2xl p-6">
            <div className="text-4xl mb-4">{f.icon}</div>
            <h3 className="text-xl font-semibold mb-2">{f.title}</h3>
            <p className="text-gray-400 text-sm">{f.desc}</p>
          </div>
        ))}
      </section>

      {/* Pricing */}
      <section className="max-w-3xl mx-auto px-6 py-20 text-center">
        <h2 className="text-3xl font-bold mb-12">Pricing</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="bg-gray-900 rounded-2xl p-8 border border-gray-800">
            <h3 className="text-xl font-bold mb-2">Plus</h3>
            <p className="text-4xl font-bold mb-4">
              $9<span className="text-lg text-gray-400">/mo</span>
            </p>
            <ul className="text-gray-400 text-sm space-y-2 mb-8 text-left">
              <li>✓ 5 job categories</li>
              <li>✓ Daily digest</li>
              <li>✓ Semantic matching</li>
            </ul>
            <a
              href={process.env.NEXT_PUBLIC_STRIPE_PLUS_URL ?? "#"}
              className="block bg-indigo-600 hover:bg-indigo-500 text-white font-semibold py-3 rounded-xl transition"
            >
              Get Plus
            </a>
          </div>
          <div className="bg-indigo-900 rounded-2xl p-8 border border-indigo-600">
            <h3 className="text-xl font-bold mb-2">Pro Plus</h3>
            <p className="text-4xl font-bold mb-4">
              $19<span className="text-lg text-indigo-300">/mo</span>
            </p>
            <ul className="text-indigo-200 text-sm space-y-2 mb-8 text-left">
              <li>✓ Unlimited categories</li>
              <li>✓ Hourly updates</li>
              <li>✓ Priority support</li>
            </ul>
            <a
              href={process.env.NEXT_PUBLIC_STRIPE_PRO_PLUS_URL ?? "#"}
              className="block bg-white text-indigo-900 font-semibold py-3 rounded-xl transition hover:bg-indigo-100"
            >
              Get Pro Plus
            </a>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-gray-800 text-center text-gray-600 text-sm py-8">
        © {new Date().getFullYear()} Vacancy Mirror ·{" "}
        <a href="mailto:admin@vacancy-mirror.com" className="hover:text-gray-400">
          Contact
        </a>
      </footer>
    </main>
  );
}
