import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Privacy Policy & Terms of Use",
  description:
    "Vacancy Mirror privacy policy, terms of use, refund policy, and subscription terms. " +
    "We analyse public market data only. " +
    "Effective April 7, 2026.",
  alternates: { canonical: "https://vacancy-mirror.com/privacy" },
  openGraph: {
    url: "https://vacancy-mirror.com/privacy",
    title: "Privacy Policy & Terms of Use | Vacancy Mirror",
    description:
      "Vacancy Mirror privacy policy, terms of use, refund policy, and subscription terms. " +
      "Effective April 7, 2026.",
  },
  robots: { index: false, follow: false },
};

export default function PrivacyPage() {
  return (
    <main className="min-h-screen bg-gray-950 text-white">
      <div className="max-w-3xl mx-auto px-6 py-20">
        <a
          href="/"
          className="text-indigo-400 text-sm hover:underline mb-8 inline-block"
        >
          ← Back to home
        </a>

        <h1 className="text-4xl font-semibold tracking-tight mb-2">
          Privacy Policy &amp; Terms of Use
        </h1>
        <p className="text-gray-500 text-sm mb-12">
          Effective date: April 7, 2026
        </p>

        <div className="space-y-10 text-gray-300 leading-relaxed">
          <Section title="1. About Vacancy Mirror">
            <p>
              Vacancy Mirror is an independent freelance market intelligence
              tool designed to help freelancers understand market demand through
              semantic search, trend analysis, clustering, and AI-generated
              insights.
            </p>
            <p className="mt-3">
              Vacancy Mirror is not affiliated with, endorsed by, sponsored by,
              or officially connected to Upwork Inc., Telegram, Google, or any
              other third-party platform. All trademarks, logos, and platform
              names remain the property of their respective owners.
            </p>
          </Section>

          <Section title="2. Eligibility">
            <p>
              You must be at least 18 years old (or the age of majority in
              your jurisdiction) to use Vacancy Mirror. By using the service
              or purchasing a subscription, you confirm that you meet this
              requirement.
            </p>
          </Section>

          <Section title="3. Data Sources">
            <p>
              Vacancy Mirror analyses information that is publicly available on
              the internet, including public job listings, search engine results,
              job titles, descriptions, skills, categories, budgets, and
              metadata.
            </p>
            <p className="mt-3">
              We do not require or request usernames, passwords, cookies, API
              keys, session tokens, or browser credentials. We do not access
              private accounts, dashboards, messages, proposals, contracts, or
              payment information.
            </p>
          </Section>

          <Section title="4. Read-Only Service">
            <p>Vacancy Mirror is strictly a read-only analytical service. The service does not:</p>
            <ul className="mt-3 space-y-1 list-none">
              {[
                "Submit proposals or apply to jobs",
                "Contact clients or send messages",
                "Log into third-party platforms on your behalf",
                "Automate account activity",
                "Take any action using your Upwork or other platform account",
              ].map((item) => (
                <li key={item} className="flex gap-2">
                  <span className="text-indigo-400">▸</span> {item}
                </li>
              ))}
            </ul>
          </Section>

          <Section title="5. AI-Generated Insights">
            <p>
              Vacancy Mirror uses AI to generate market summaries, trend
              reports, skill recommendations, search results, and role clusters.
              AI-generated insights may occasionally be incomplete, inaccurate,
              delayed, or based on limited data.
            </p>
            <p className="mt-3">
              Vacancy Mirror does not guarantee hiring success, accuracy or
              completeness of all data, or availability of specific jobs. You
              should independently verify important decisions before relying on
              the service.
            </p>
          </Section>

          <Section title="6. Subscription & Payment Terms">
            <p>
              Vacancy Mirror offers free and paid subscription plans. Paid
              plans are billed monthly in US Dollars (USD) and automatically
              renew at the end of each billing cycle unless you cancel before
              the renewal date.
            </p>
            <p className="mt-3">
              All payments are processed securely by{" "}
              <a
                href="https://stripe.com"
                target="_blank"
                rel="noopener noreferrer"
                className="text-indigo-400 hover:underline"
              >
                Stripe
              </a>
              . We do not store your credit card number, CVV, or full payment
              details on our servers. Stripe&apos;s privacy policy governs the
              handling of your payment data.
            </p>
            <p className="mt-3">
              If a payment fails, your subscription may be paused or
              downgraded to the free plan until the payment issue is resolved.
              We reserve the right to change pricing with at least 30 days&apos;
              notice before the next billing cycle.
            </p>
          </Section>

          <Section title="7. Cancellation & Refund Policy">
            <p>
              You may cancel your subscription at any time by contacting us at{" "}
              <a
                href="mailto:support@vacancy-mirror.com"
                className="text-indigo-400 hover:underline"
              >
                support@vacancy-mirror.com
              </a>
              . Upon cancellation:
            </p>
            <ul className="mt-3 space-y-1">
              {[
                "Your paid features remain active until the end of the current billing period",
                "Your account will automatically revert to the free plan after that period ends",
                "No further charges will be made after cancellation",
              ].map((item) => (
                <li key={item} className="flex gap-2">
                  <span className="text-indigo-400">▸</span> {item}
                </li>
              ))}
            </ul>
            <p className="mt-3 font-medium text-white">Refunds:</p>
            <ul className="mt-2 space-y-1">
              {[
                "If you cancel within 48 hours of your first subscription payment and have not extensively used paid features, you may request a full refund",
                "Refund requests after the 48-hour window are evaluated on a case-by-case basis",
                "Renewal charges are non-refundable once the new billing cycle has started, unless required by applicable law",
                "EU/EEA/UK consumers may have additional rights under applicable consumer protection laws",
              ].map((item) => (
                <li key={item} className="flex gap-2">
                  <span className="text-indigo-400">▸</span> {item}
                </li>
              ))}
            </ul>
            <p className="mt-3">
              To request a refund, email{" "}
              <a
                href="mailto:support@vacancy-mirror.com"
                className="text-indigo-400 hover:underline"
              >
                support@vacancy-mirror.com
              </a>{" "}
              with your Telegram username and a brief explanation.
            </p>
          </Section>

          <Section title="8. Your Data">
            <p>To provide the service, we may store:</p>
            <ul className="mt-3 space-y-1">
              {[
                "Your Telegram user ID and username",
                "Messages you send to the bot",
                "Search history and saved preferences",
                "Generated reports",
                "Technical logs (timestamps, language settings)",
                "Subscription status and Stripe customer ID (no card details)",
              ].map((item) => (
                <li key={item} className="flex gap-2">
                  <span className="text-indigo-400">▸</span> {item}
                </li>
              ))}
            </ul>
            <p className="mt-3">
              We use this information only to provide and improve the service.
              We do not sell, rent, or share your personal data with advertisers
              or unrelated third parties.
            </p>
          </Section>

          <Section title="9. Data Retention">
            <p>
              We keep your data only as long as reasonably necessary to provide
              the service. Chat history may be automatically removed after a
              reasonable period. You may request deletion of your data at any
              time.
            </p>
          </Section>

          <Section title="10. GDPR & EU Rights">
            <p>
              If you are located in the EU, EEA, or UK, you have the right to
              access, correct, delete, restrict, export your data, and withdraw
              consent at any time. Contact us to exercise these rights.
            </p>
          </Section>

          <Section title="11. Security">
            <p>
              We take reasonable technical and organisational measures to
              protect your information, including encrypted connections and
              restricted access to stored data. However, no internet service can
              be guaranteed to be completely secure. You use the service at your
              own risk.
            </p>
          </Section>

          <Section title="12. Intellectual Property">
            <p>
              All job listings, platform names, trademarks, and third-party
              content remain the property of their respective owners. Vacancy
              Mirror only provides independent analysis and does not claim
              ownership of any third-party content.
            </p>
          </Section>

          <Section title="13. Disclaimer of Warranties">
            <p>
              The service is provided <strong>&quot;as is&quot;</strong> and{" "}
              <strong>&quot;as available&quot;</strong> without warranties of
              any kind, whether express or implied, including but not limited to
              implied warranties of merchantability, fitness for a particular
              purpose, or non-infringement.
            </p>
            <p className="mt-3">
              We do not warrant that the service will be uninterrupted,
              error-free, secure, or available at any particular time. Market
              data, AI insights, and analytics may be delayed, incomplete, or
              inaccurate. The service is not professional career advice.
            </p>
          </Section>

          <Section title="14. Limitation of Liability">
            <p>
              To the maximum extent permitted by applicable law, Vacancy Mirror
              and its operators shall not be liable for any indirect,
              incidental, special, consequential, or punitive damages, including
              but not limited to loss of profits, revenue, data, business
              opportunities, or goodwill, arising out of or in connection with
              your use of the service.
            </p>
            <p className="mt-3">
              Our total aggregate liability for any claims arising from or
              relating to the service shall not exceed the amount you paid to
              Vacancy Mirror in the three (3) months preceding the event giving
              rise to the claim.
            </p>
          </Section>

          <Section title="15. Service Availability">
            <p>
              We strive to maintain high availability but do not guarantee any
              specific uptime level. The service may be temporarily unavailable
              due to maintenance, updates, server issues, or circumstances
              beyond our control. We will make reasonable efforts to notify
              users of planned downtime in advance.
            </p>
          </Section>

          <Section title="16. Prohibited Use">
            <p>You may not use Vacancy Mirror to:</p>
            <ul className="mt-3 space-y-1">
              {[
                "Break the law or violate third-party platform rules",
                "Spam, harass, or abuse others",
                "Automate proposals, bidding, or messaging",
                "Reverse engineer or abuse the service",
                "Resell or copy the service without permission",
              ].map((item) => (
                <li key={item} className="flex gap-2">
                  <span className="text-indigo-400">▸</span> {item}
                </li>
              ))}
            </ul>
          </Section>

          <Section title="17. Termination">
            <p>
              We reserve the right to suspend or terminate your access to
              Vacancy Mirror at any time, with or without notice, if we
              reasonably believe you have violated these Terms or engaged in
              prohibited use. Upon termination for cause, no refund will be
              issued for the remaining subscription period.
            </p>
            <p className="mt-3">
              You may terminate your use of the service at any time by
              cancelling your subscription and ceasing to use the bot.
            </p>
          </Section>

          <Section title="18. Governing Law & Disputes">
            <p>
              These Terms are governed by and construed in accordance with the
              laws of the Republic of Lithuania. Any disputes arising from or
              relating to these Terms or your use of the service shall be
              resolved in the courts of Vilnius, Lithuania, unless mandatory
              consumer protection laws in your jurisdiction require otherwise.
            </p>
            <p className="mt-3">
              Before filing any formal complaint, we encourage you to contact
              us at{" "}
              <a
                href="mailto:support@vacancy-mirror.com"
                className="text-indigo-400 hover:underline"
              >
                support@vacancy-mirror.com
              </a>{" "}
              so we can attempt to resolve the issue informally.
            </p>
          </Section>

          <Section title="19. Changes">
            <p>
              We may update these Terms and Privacy Policy at any time. The
              latest version will always be available on this page and inside
              the bot. Material changes will be communicated via the bot or
              email at least 14 days before taking effect. By continuing to
              use Vacancy Mirror after changes take effect, you agree to the
              updated Terms.
            </p>
          </Section>

          <Section title="20. Contact">
            <p>
              For support, privacy requests, refunds, or data deletion:{" "}
              <a
                href="mailto:support@vacancy-mirror.com"
                className="text-indigo-400 hover:underline"
              >
                support@vacancy-mirror.com
              </a>
            </p>
          </Section>
        </div>
      </div>
    </main>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <h2 className="text-lg font-semibold text-white mb-3">{title}</h2>
      {children}
    </section>
  );
}
