import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Features — 7 AI Tools for Upwork Freelancers",
  description:
    "Vacancy Mirror gives you 7 tools to grow on Upwork: weekly market " +
    "trends, AI career assistant, profile optimisation, portfolio agent, " +
    "and skills reports — free and paid plans.",
  alternates: { canonical: "https://vacancy-mirror.com/benefits" },
  openGraph: {
    url: "https://vacancy-mirror.com/benefits",
    title: "Features — 7 AI Tools for Upwork Freelancers | Vacancy Mirror",
    description:
      "Weekly Upwork market trends, AI profile optimisation, portfolio " +
      "recommendations, and more — free and paid plans.",
  },
};

const features = [
  {
    id: "trends-report",
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
    id: "ai-assistant",
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
    id: "trend-charts",
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
    id: "profile-optimisation",
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
    id: "projects-agent",
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
    id: "extended-projects-agent",
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
    id: "skills-tags-report",
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
  const jsonLd = [
    {
      "@context": "https://schema.org",
      "@type": "BreadcrumbList",
      itemListElement: [
        {
          "@type": "ListItem",
          position: 1,
          name: "Home",
          item: "https://vacancy-mirror.com",
        },
        {
          "@type": "ListItem",
          position: 2,
          name: "Features",
          item: "https://vacancy-mirror.com/benefits",
        },
      ],
    },
    {
      "@context": "https://schema.org",
      "@type": "ItemList",
      name: "Vacancy Mirror Features",
      description: "7 AI-powered tools for Upwork freelancers",
      url: "https://vacancy-mirror.com/benefits",
      numberOfItems: features.length,
      itemListElement: features.map((f, i) => ({
        "@type": "ListItem",
        position: i + 1,
        name: f.title,
        description: f.summary,
        url: `https://vacancy-mirror.com/benefits#${f.id}`,
      })),
    },
  ];

  return (
    <main className="min-h-screen bg-gray-950 text-white">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
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
              id={f.id}
              className="bg-white/5 border border-white/10 rounded-2xl p-8 scroll-mt-24"
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

        {/* Community section */}
        <div className="mt-16 bg-gradient-to-br from-indigo-900/40 to-violet-900/30 border border-indigo-500/30 rounded-2xl p-8 text-center">
          <div className="text-4xl mb-4">🌐</div>
          <h2 className="text-2xl font-semibold mb-3">
            Vacancy Mirror | International Community
          </h2>
          <p className="text-gray-400 text-sm max-w-xl mx-auto mb-6">
            Join our Telegram community of freelancers who share market
            insights, discuss Upwork trends, swap tips on proposals and
            profiles, and support each other on the road to Top Rated.
          </p>
          <a
            href="https://t.me/VacancyMirror"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold px-8 py-3 rounded-xl text-sm transition-colors"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="currentColor"
              className="w-5 h-5"
            >
              <path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z" />
            </svg>
            Join the Community
          </a>
        </div>

        <div className="mt-10 text-center">
          <p className="text-gray-400 mb-6">
            Ready to start? All free features are available immediately.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <a
              href="https://t.me/VacancyMirror"
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
