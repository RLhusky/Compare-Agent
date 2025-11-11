import { Header } from './Header';
import { Footer } from './Footer';
import { Search, TrendingUp, Award } from 'lucide-react';

export function HowItWorksPage() {
  return (
    <div className="min-h-screen bg-white">
      <Header />
      
      <div className="max-w-4xl mx-auto px-4 py-16">
        <h1 className="text-center text-gray-900 mb-6" style={{ fontSize: '48px', fontWeight: 700 }}>
          How It Works
        </h1>
        
        <p className="text-center text-gray-600 mb-16 max-w-2xl mx-auto" style={{ fontSize: '18px' }}>
          Comparoo uses advanced AI to analyze thousands of products and provide you with unbiased, data-driven recommendations.
        </p>
        
        <div className="space-y-16">
          {/* Step 1 */}
          <div className="flex flex-col md:flex-row gap-8 items-start">
            <div className="flex-shrink-0">
              <div className="w-16 h-16 rounded-full bg-emerald-100 flex items-center justify-center">
                <Search className="h-8 w-8 text-emerald-600" />
              </div>
            </div>
            <div className="flex-1">
              <h3 className="text-gray-900 mb-3" style={{ fontSize: '24px', fontWeight: 600 }}>
                1. Search for Products
              </h3>
              <p className="text-gray-600" style={{ fontSize: '16px' }}>
                Simply enter the product category you're interested in. Our AI will instantly search through our extensive database of analyzed products to find the best options for you.
              </p>
            </div>
          </div>
          
          {/* Step 2 */}
          <div className="flex flex-col md:flex-row gap-8 items-start">
            <div className="flex-shrink-0">
              <div className="w-16 h-16 rounded-full bg-emerald-100 flex items-center justify-center">
                <TrendingUp className="h-8 w-8 text-emerald-600" />
              </div>
            </div>
            <div className="flex-1">
              <h3 className="text-gray-900 mb-3" style={{ fontSize: '24px', fontWeight: 600 }}>
                2. AI Analysis
              </h3>
              <p className="text-gray-600" style={{ fontSize: '16px' }}>
                Our sophisticated AI analyzes hundreds of data points including customer reviews, expert opinions, performance metrics, and price trends to give you the most accurate comparison.
              </p>
            </div>
          </div>
          
          {/* Step 3 */}
          <div className="flex flex-col md:flex-row gap-8 items-start">
            <div className="flex-shrink-0">
              <div className="w-16 h-16 rounded-full bg-emerald-100 flex items-center justify-center">
                <Award className="h-8 w-8 text-emerald-600" />
              </div>
            </div>
            <div className="flex-1">
              <h3 className="text-gray-900 mb-3" style={{ fontSize: '24px', fontWeight: 600 }}>
                3. Clear Comparisons
              </h3>
              <p className="text-gray-600" style={{ fontSize: '16px' }}>
                View side-by-side comparisons, detailed scorecards, and comprehensive reviews. Make informed decisions with confidence, backed by unbiased AI-powered insights.
              </p>
            </div>
          </div>
        </div>
        
        <div className="mt-16 p-8 bg-emerald-50 rounded-2xl">
          <h3 className="text-gray-900 mb-4 text-center" style={{ fontSize: '24px', fontWeight: 600 }}>
            Why Trust Comparoo?
          </h3>
          <p className="text-gray-600 text-center max-w-2xl mx-auto" style={{ fontSize: '16px' }}>
            We don't accept paid placements or sponsored reviews. Our AI-powered analysis is completely unbiased, ensuring you get honest recommendations based purely on product quality and value.
          </p>
        </div>
      </div>
      
      <Footer />
    </div>
  );
}
