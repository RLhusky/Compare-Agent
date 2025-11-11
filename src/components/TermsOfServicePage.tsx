import { Header } from './Header';
import { Footer } from './Footer';

export function TermsOfServicePage() {
  return (
    <div className="min-h-screen bg-white">
      <Header />
      
      <main className="max-w-4xl mx-auto px-4 py-12">
        <h1 className="text-black mb-2" style={{ fontSize: '36px', fontWeight: 700 }}>
          Terms of Service
        </h1>
        <p className="text-gray-600 mb-8">Last Updated: November 8, 2025</p>
        
        <div className="space-y-8 text-black">
          {/* Section 1 */}
          <section>
            <h2 className="mb-3" style={{ fontSize: '24px', fontWeight: 600 }}>
              1. Agreement to Terms
            </h2>
            <p className="text-gray-700 leading-relaxed">
              By accessing or using Comparoo (&quot;Service&quot;), you agree to be bound by these Terms of Service (&quot;Terms&quot;). If you disagree with any part of these terms, you may not access the Service.
            </p>
          </section>

          {/* Section 2 */}
          <section>
            <h2 className="mb-3" style={{ fontSize: '24px', fontWeight: 600 }}>
              2. Description of Service
            </h2>
            <p className="text-gray-700 leading-relaxed">
              Comparoo is an AI-powered product comparison platform that aggregates and analyzes expert reviews from third-party sources to help users make informed purchasing decisions. We do not sell products, accept affiliate commissions, or receive compensation for product recommendations.
            </p>
          </section>

          {/* Section 3 */}
          <section>
            <h2 className="mb-3" style={{ fontSize: '24px', fontWeight: 600 }}>
              3. Use of Service
            </h2>
            <h3 className="mb-2 mt-4" style={{ fontSize: '18px', fontWeight: 600 }}>
              3.1 Permitted Use
            </h3>
            <p className="text-gray-700 leading-relaxed mb-2">You may use Comparoo to:</p>
            <ul className="list-disc pl-6 text-gray-700 space-y-1">
              <li>Search for and view product comparisons</li>
              <li>Access AI-generated analysis of expert reviews</li>
              <li>Browse product categories and recommendations</li>
            </ul>

            <h3 className="mb-2 mt-4" style={{ fontSize: '18px', fontWeight: 600 }}>
              3.2 Prohibited Use
            </h3>
            <p className="text-gray-700 leading-relaxed mb-2">You may not:</p>
            <ul className="list-disc pl-6 text-gray-700 space-y-1">
              <li>Use the Service for any illegal purpose</li>
              <li>Attempt to scrape, copy, or systematically download content from the Service</li>
              <li>Reverse engineer or attempt to extract source code from the Service</li>
              <li>Use automated systems (bots, scrapers) to access the Service without permission</li>
              <li>Misrepresent your affiliation with any person or entity</li>
              <li>Interfere with or disrupt the Service or servers</li>
            </ul>
          </section>

          {/* Section 4 */}
          <section>
            <h2 className="mb-3" style={{ fontSize: '24px', fontWeight: 600 }}>
              4. AI-Generated Content Disclaimer
            </h2>
            <p className="text-gray-700 leading-relaxed mb-3">
              <strong>IMPORTANT:</strong> Comparoo uses artificial intelligence to analyze and summarize product reviews. While we strive for accuracy:
            </p>
            <ul className="list-disc pl-6 text-gray-700 space-y-1 mb-3">
              <li>AI-generated comparisons may contain errors or inaccuracies</li>
              <li>Information is based on available expert reviews at the time of generation</li>
              <li>Product details, prices, and availability change frequently</li>
              <li>Our analysis should be used as one of many factors in your purchasing decision</li>
            </ul>
            <p className="text-gray-700 leading-relaxed">
              You are solely responsible for verifying information before making any purchase.
            </p>
          </section>

          {/* Section 5 */}
          <section>
            <h2 className="mb-3" style={{ fontSize: '24px', fontWeight: 600 }}>
              5. Third-Party Content
            </h2>
            <h3 className="mb-2 mt-4" style={{ fontSize: '18px', fontWeight: 600 }}>
              5.1 Review Sources
            </h3>
            <p className="text-gray-700 leading-relaxed mb-2">Comparoo aggregates content from third-party expert review sites. We do not:</p>
            <ul className="list-disc pl-6 text-gray-700 space-y-1">
              <li>Control or verify the accuracy of third-party reviews</li>
              <li>Endorse any specific products or manufacturers</li>
              <li>Guarantee the availability or accuracy of external links</li>
            </ul>

            <h3 className="mb-2 mt-4" style={{ fontSize: '18px', fontWeight: 600 }}>
              5.2 Product Purchases
            </h3>
            <p className="text-gray-700 leading-relaxed mb-2">Any purchases you make are transactions between you and the retailer/manufacturer. Comparoo is not responsible for:</p>
            <ul className="list-disc pl-6 text-gray-700 space-y-1">
              <li>Product quality, safety, or performance</li>
              <li>Shipping, returns, or customer service</li>
              <li>Pricing accuracy or availability</li>
              <li>Warranty claims or defects</li>
            </ul>
          </section>

          {/* Section 6 */}
          <section>
            <h2 className="mb-3" style={{ fontSize: '24px', fontWeight: 600 }}>
              6. Intellectual Property
            </h2>
            <h3 className="mb-2 mt-4" style={{ fontSize: '18px', fontWeight: 600 }}>
              6.1 Our Content
            </h3>
            <p className="text-gray-700 leading-relaxed mb-3">
              The Comparoo platform, including its design, functionality, AI-generated comparisons, and original content, is owned by Comparoo and protected by copyright and other intellectual property laws.
            </p>

            <h3 className="mb-2 mt-4" style={{ fontSize: '18px', fontWeight: 600 }}>
              6.2 Third-Party Content
            </h3>
            <p className="text-gray-700 leading-relaxed mb-3">
              Expert reviews and product information are owned by their respective publishers. We aggregate and analyze this content under fair use principles for informational purposes.
            </p>

            <h3 className="mb-2 mt-4" style={{ fontSize: '18px', fontWeight: 600 }}>
              6.3 Your Use
            </h3>
            <p className="text-gray-700 leading-relaxed mb-2">You may not:</p>
            <ul className="list-disc pl-6 text-gray-700 space-y-1">
              <li>Reproduce, distribute, or create derivative works from our content</li>
              <li>Use our content for commercial purposes without permission</li>
              <li>Remove copyright notices or attributions</li>
            </ul>
          </section>

          {/* Section 7 */}
          <section>
            <h2 className="mb-3" style={{ fontSize: '24px', fontWeight: 600 }}>
              7. Limitation of Liability
            </h2>
            <p className="text-gray-700 leading-relaxed mb-3">
              <strong>TO THE MAXIMUM EXTENT PERMITTED BY LAW:</strong>
            </p>
            <p className="text-gray-700 leading-relaxed mb-2">
              Comparoo and its officers, directors, employees, and agents shall not be liable for:
            </p>
            <ul className="list-disc pl-6 text-gray-700 space-y-1 mb-3">
              <li>Any indirect, incidental, special, consequential, or punitive damages</li>
              <li>Loss of profits, revenue, data, or use</li>
              <li>Damage arising from your reliance on information from the Service</li>
              <li>Inaccurate product information or AI-generated content</li>
              <li>Poor purchasing decisions based on our comparisons</li>
              <li>Any damages arising from third-party products or services</li>
            </ul>
            <p className="text-gray-700 leading-relaxed">
              THE SERVICE IS PROVIDED &quot;AS IS&quot; WITHOUT WARRANTIES OF ANY KIND.
            </p>
          </section>

          {/* Section 8 */}
          <section>
            <h2 className="mb-3" style={{ fontSize: '24px', fontWeight: 600 }}>
              8. Indemnification
            </h2>
            <p className="text-gray-700 leading-relaxed mb-2">
              You agree to indemnify and hold harmless Comparoo from any claims, damages, losses, liabilities, and expenses (including legal fees) arising from:
            </p>
            <ul className="list-disc pl-6 text-gray-700 space-y-1">
              <li>Your use of the Service</li>
              <li>Your violation of these Terms</li>
              <li>Your violation of any rights of another party</li>
            </ul>
          </section>

          {/* Section 9 */}
          <section>
            <h2 className="mb-3" style={{ fontSize: '24px', fontWeight: 600 }}>
              9. Privacy
            </h2>
            <p className="text-gray-700 leading-relaxed">
              Your use of the Service is also governed by our Privacy Policy. By using Comparoo, you consent to our collection and use of data as described in that policy.
            </p>
          </section>

          {/* Section 10 */}
          <section>
            <h2 className="mb-3" style={{ fontSize: '24px', fontWeight: 600 }}>
              10. Changes to Service
            </h2>
            <p className="text-gray-700 leading-relaxed mb-2">We reserve the right to:</p>
            <ul className="list-disc pl-6 text-gray-700 space-y-1">
              <li>Modify or discontinue the Service at any time without notice</li>
              <li>Change these Terms at any time</li>
              <li>Refuse service to anyone for any reason</li>
            </ul>
            <p className="text-gray-700 leading-relaxed mt-3">
              Continued use of the Service after changes constitutes acceptance of modified Terms.
            </p>
          </section>

          {/* Section 11 */}
          <section>
            <h2 className="mb-3" style={{ fontSize: '24px', fontWeight: 600 }}>
              11. Termination
            </h2>
            <p className="text-gray-700 leading-relaxed">
              We may terminate or suspend your access to the Service immediately, without prior notice, for any reason, including breach of these Terms.
            </p>
          </section>

          {/* Section 12 */}
          <section>
            <h2 className="mb-3" style={{ fontSize: '24px', fontWeight: 600 }}>
              12. Governing Law
            </h2>
            <p className="text-gray-700 leading-relaxed mb-2">
              These Terms shall be governed by the laws of the State of Delaware, United States, without regard to its conflict of law provisions.
            </p>
            <p className="text-gray-700 leading-relaxed">
              Any disputes arising from these Terms or the Service shall be resolved in the courts of Delaware.
            </p>
          </section>

          {/* Section 13 */}
          <section>
            <h2 className="mb-3" style={{ fontSize: '24px', fontWeight: 600 }}>
              13. Severability
            </h2>
            <p className="text-gray-700 leading-relaxed">
              If any provision of these Terms is held to be unenforceable, that provision shall be removed and the remaining provisions shall remain in full effect.
            </p>
          </section>

          {/* Section 14 */}
          <section>
            <h2 className="mb-3" style={{ fontSize: '24px', fontWeight: 600 }}>
              14. Entire Agreement
            </h2>
            <p className="text-gray-700 leading-relaxed">
              These Terms constitute the entire agreement between you and Comparoo regarding the Service and supersede any prior agreements.
            </p>
          </section>

          {/* Section 15 */}
          <section>
            <h2 className="mb-3" style={{ fontSize: '24px', fontWeight: 600 }}>
              15. Contact Information
            </h2>
            <p className="text-gray-700 leading-relaxed">
              For questions about these Terms, please contact us at:
            </p>
            <p className="text-gray-700 leading-relaxed mt-2">
              <strong>Email:</strong> nicholas.comparoo@gmail.com
            </p>
          </section>

          {/* Section 16 */}
          <section>
            <h2 className="mb-3" style={{ fontSize: '24px', fontWeight: 600 }}>
              16. Acknowledgment
            </h2>
            <p className="text-gray-700 leading-relaxed">
              BY USING COMPAROO, YOU ACKNOWLEDGE THAT YOU HAVE READ THESE TERMS, UNDERSTAND THEM, AND AGREE TO BE BOUND BY THEM.
            </p>
          </section>
        </div>
      </main>

      <Footer />
    </div>
  );
}
