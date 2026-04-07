import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Pricing",
  description:
    "Free, Plus ($9.99/mo) and Pro Plus ($19.99/mo) plans for " +
    "Upwork freelancers. Start free, upgrade for AI profile advice " +
    "and portfolio recommendations.",
  alternates: { canonical: "https://vacancy-mirror.com/pricing" },
  openGraph: {
    url: "https://vacancy-mirror.com/pricing",
    title: "Pricing | Vacancy Mirror",
    description:
      "Free, Plus and Pro Plus plans for Upwork freelancers. " +
      "Cancel anytime.",
  },
};

const PLUS_URL = process.env.NEXT_PUBLIC_STRIPE_PLUS_URL ?? "#";
const PRO_PLUS_URL = process.env.NEXT_PUBLIC_STRIPE_PRO_PLUS_URL ?? "#";

const plans = [
  {
    name: "Free",
    price: "$0",
    period: "forever",
    description: "Get started with daily AI insights, no card required.",
    features: [
      "35 AI messages / day",
      "Weekly Trends Report",
      "Weekly Trend Charts",
    ],
    cta: "Start in Telegram",
    href: "https://t.me/VacancyMirrorBot",
    highlighted: false,
  },
  {
    name: "Plus",
    price: "$9.99",
    period: "/ month",
    description: "Optimise your profile and grow your project portfolio.",
    features: [
      "60 AI messages / day",
      "Profile Optimisation Expert",
      "Weekly Profile & Projects Agent",
      "Up to 5 portfolio projects reviewed",
    ],
    cta: "Subscribe — $9.99 / mo",
    href: PLUS_URL,
    highlighted: true,
  },
  {
    name: "Pro Plus",
    price: "$19.99",
    period: "/ month",
    description: "Full market coverage for serious freelancers.",
    features: [
      "120 AI messages / day",
      "Extended Projects Agent",
      "Up to 12 portfolio projects reviewed",
      "Weekly Skills & Tags Report",
      "Full portfolio aligned with market trends",
    ],
    cta: "Subscribe — $19.99 / mo",
    href: PRO_PLUS_URL,
    highlighted: false,
    comingSoon: true,
  },
];

export default function PricingPage() {
  return (
    <main className="min-h-screen bg-gray-950 text-white">
      <div className="max-w-5xl mx-auto px-6 py-20">
        <a
          href="/"
          className="text-indigo-400 text-sm hover:underline mb-10 inline-block"
        >
          ← Back to home
        </a>

        <div className="text-center mb-16">
          <h1 className="text-4xl font-semibold tracking-tight mb-4">
            Simple, transparent pricing
          </h1>
          <p className="text-gray-400 text-lg max-w-xl mx-auto">
            Start free. Upgrade when you need deeper market intelligence and
            AI-powered profile optimisation.
          </p>
        </div>

        <div className="grid md:grid-cols-3 gap-6">
          {plans.map((plan) => (
            <PlanCard key={plan.name} plan={plan} />
          ))}
        </div>

        <p className="text-center text-gray-600 text-sm mt-12">
          All paid plans are billed monthly. Cancel anytime.{" "}
          <a href="/privacy" className="text-indigo-400 hover:underline">
            Privacy Policy
          </a>
        </p>
      </div>
    </main>
  );
}

function PlanCard({
  plan,
}: {
  plan: (typeof plans)[number];
}) {
  return (
    <div
      className={`relative flex flex-col rounded-2xl border p-8 ${
        plan.highlighted
          ? "border-indigo-500 bg-indigo-950/40 shadow-[0_0_40px_-10px_rgba(99,102,241,0.4)]"
          : "border-white/10 bg-white/5"
      }`}
    >
      {plan.highlighted && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2">
          <span className="bg-indigo-500 text-white text-xs font-semibold px-3 py-1 rounded-full">
            Most popular
          </span>
        </div>
      )}

      {plan.comingSoon && (
        <div className="absolute top-4 right-4">
          <span className="bg-amber-500/20 border border-amber-400/40 text-amber-300 text-xs font-semibold px-2.5 py-1 rounded-full">
            Coming soon
          </span>
        </div>
      )}

      <div className="mb-6">
        <h2 className="text-lg font-semibold mb-1">{plan.name}</h2>
        <div className="flex items-end gap-1 mb-3">
          <span className="text-4xl font-bold">{plan.price}</span>
          <span className="text-gray-400 pb-1 text-sm">{plan.period}</span>
        </div>
        <p className="text-gray-400 text-sm">{plan.description}</p>
      </div>

      <ul className="space-y-3 mb-8 flex-1">
        {plan.features.map((feature) => (
          <li key={feature} className="flex items-start gap-2 text-sm">
            <span className="text-indigo-400 mt-0.5">✓</span>
            <span className="text-gray-300">{feature}</span>
          </li>
        ))}
      </ul>

      {plan.comingSoon ? (
        <div className="w-full text-center py-3 rounded-xl text-sm font-semibold bg-white/5 text-gray-400 border border-white/10 cursor-not-allowed">
          Coming soon
        </div>
      ) : (
        <a
          href={plan.href}
          target={plan.href.startsWith("http") ? "_blank" : undefined}
          rel="noopener noreferrer"
          className={`w-full text-center py-3 rounded-xl text-sm font-semibold transition-all ${
            plan.highlighted
              ? "bg-indigo-600 hover:bg-indigo-500 text-white"
              : "bg-white/10 hover:bg-white/20 text-white"
          }`}
        >
          {plan.cta}
        </a>
      )}
    </div>
  );
}
