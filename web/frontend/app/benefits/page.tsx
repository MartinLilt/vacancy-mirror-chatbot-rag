import Link from "next/link";

const features = [
  {
    badge: "Free",
    badgeColor: "bg-gray-700 text-gray-300",
    icon: "📊",
    title: "Weekly Freelance Trends Report",
    summary:
      "Once a week, Vacancy Mirror sends you a summary of how the " +
      "freelance market changed over the last 7 days.",
    bullets: [
      "Which roles and skills are growing or declining",
      "What clients are searching for most often",
      "Which technologies and niches are becoming more popular",
      "How demand changed across Upwork categories",
    ],
    note: "Based on publicly available market data only.",
  },
  {
    badge: "Free",
    badgeColor: "bg-gray-700 text-gray-300",
    icon: "💬",
    title: "AI Market Assistant",
    summary:
      "Chat with an AI assistant about the freelance market.",
    bullets: [
      "Choose the right direction across all 12 Upwork categories",
      "Understand which skills are worth learning",
      "Compare roles, niches, and technologies",
      "Build a career roadmap from beginner to Top Rated Plus",
      "Improve your proposals, profile structure, and positioning",
    ],
    note:
      "Provides guidance and recommendations only. Does not access " +
      "your Upwork account or take any actions for you. " +
      "Limit: 35 messages / 24 h (Free) · 60 (Plus) · 120 (Pro Plus).",
  },
  {
    badge: "Free",
    badgeColor: "bg-gray-700 text-gray-300",
    icon: "📈",
    title: "Weekly Trend Charts",
    summary:
      "Receive simple charts every week comparing the current week " +
      "with the previous one.",
    bullets: [
      "Which niches are growing or shrinking",
      "Which skills are becoming more or less popular",
      "How the freelance market is changing over time",
    ],
    note: "Charts are created from publicly available job market data.",
  },
  {
    badge: "Plus",
    badgeColor: "bg-indigo-600 text-indigo-100",
    icon: "🎯",
    title: "Profile Optimisation Expert",
    summary:
      "Get recommendations on how to improve your freelancer profile " +
      "using current market trends.",
    bullets: [
      "Better profile titles",
      "More effective descriptions",
      "Important keywords and skills to include",
      "Better positioning for your chosen niche",
    ],
    note:
      "Vacancy Mirror does not edit or access your profile automatically. " +
      "All recommendations are for you to review and apply manually.",
  },
  {
    badge: "Plus",
    badgeColor: "bg-indigo-600 text-indigo-100",
    icon: "🤖",
    title: "Weekly Profile & Projects Agent",
    summary:
      "Once a week you receive a personalised report showing how to " +
      "update your freelancer profile and up to 5 portfolio projects.",
    bullets: [
      "Based on your saved preferences inside Vacancy Mirror",
      "Based on current public market trends",
      "Shows changes in demand since the previous week",
    ],
    note: "Does not connect to or modify your Upwork account.",
  },
  {
    badge: "Pro Plus",
    badgeColor: "bg-violet-600 text-violet-100",
    icon: "🚀",
    title: "Extended Projects Agent",
    summary:
      "Everything from the Plus plan, but with recommendations for " +
      "up to 12 portfolio projects instead of 5.",
    bullets: [
      "Full coverage of your entire portfolio",
      "All projects aligned with current market demand",
    ],
    note: null,
  },
  {
    badge: "Pro Plus",
    badgeColor: "bg-violet-600 text-violet-100",
    icon: "🏷️",
    title: "Weekly Skills & Tags Report",
    summary:
      "Every week, a report showing which keywords, tags, and skill " +
      "combinations appear most often in public freelance job listings.",
    bullets: [
      "Improve your profile",
      "Strengthen your proposals",
      "Sharpen your portfolio descriptions",
      "Better positioning in the market",
    ],
    note:
      "Provides recommendations only. Does not send proposals, update " +
      "profiles, or interact with third-party platforms.",
  },
];

export default function BenefitsPage() {
  return (
    <main className="min-h-screen bg-gray-950 text-white">
      <div className="max-w-3xl mx-auto px-6 py-20">
        <Link
          href="/"
          className="text-indigo-400 text-sm hover:underline mb-10 inline-block"
        >
          ← Back to home
        </Link>

        <div className="mb-16">
          <h1 className="text-4xl font-semibold tracking-tight mb-4">
            What Vacancy Mirror can do
          </h1>
          <p className="text-gray-400 text-lg">
            Seven tools for freelancers who want to grow on Upwork — powered
            by public market data and AI.
          </p>
        </div>

        <div className="space-y-8">
          {features.map((f) => (
            <div
              key={f.title}
              className="bg-white/5 border border-white/10 rounded-2xl p-8"
            >
              <div className="flex items-start gap-4 mb-4">
                <span className="text-3xl">{f.icon}</span>
                <div className="flex-1">
                  <div className="flex flex-wrap items-center gap-2 mb-1">
                    <h2 className="text-xl font-semibold">{f.title}</h2>
                    <span
                      className={`text-xs font-semibold px-2 py-0.5 rounded-full ${f.badgeColor}`}
                    >
                      {f.badge}
                    </span>
                  </div>
                  <p className="text-gray-400 text-sm">{f.summary}</p>
                </div>
              </div>

              <ul className="space-y-2 mb-4">
                {f.bullets.map((b) => (
                  <li key={b} className="flex items-start gap-2 text-sm text-gray-300">
                    <span className="text-indigo-400 mt-0.5">▸</span>
                    {b}
                  </li>
                ))}
              </ul>

              {f.note && (
                <p className="text-xs text-gray-600 italic">{f.note}</p>
              )}
            </div>
          ))}
        </div>

        <div className="mt-16 text-center">
          <p className="text-gray-400 mb-6">
            Ready to start? All free features are available immediately.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <a
              href="https://t.me/VacancyMirrorBot"
              target="_blank"
              rel="noopener noreferrer"
              className="bg-indigo-600 hover:bg-indigo-500 text-white font-semibold px-8 py-3 rounded-xl text-sm transition-colors"
            >
              Start in Telegram — Free
            </a>
            <Link
              href="/pricing"
              className="bg-white/10 hover:bg-white/20 text-white font-semibold px-8 py-3 rounded-xl text-sm transition-colors"
            >
              See pricing plans
            </Link>
          </div>
        </div>
      </div>
    </main>
  );
}
