import { Header } from './Header';
import { Footer } from './Footer';
import { Target, Shield, Sparkles } from 'lucide-react';

export function AboutPage() {
  return (
    <div className="min-h-screen bg-white">
      <Header />
      
      <div className="max-w-4xl mx-auto px-4 py-16">
        <h1 className="text-center text-gray-900 mb-6" style={{ fontSize: '48px', fontWeight: 700 }}>
          About Comparoo
        </h1>
        
        <p className="text-center text-gray-600 mb-16 max-w-2xl mx-auto" style={{ fontSize: '18px' }}>
          We're on a mission to help consumers make better purchasing decisions through unbiased, AI-powered product comparisons.
        </p>
        
        <div className="space-y-12 mb-16">
          {/* Mission */}
          <div className="flex flex-col md:flex-row gap-8 items-start">
            <div className="flex-shrink-0">
              <div className="w-16 h-16 rounded-full bg-emerald-100 flex items-center justify-center">
                <Target className="h-8 w-8 text-emerald-600" />
              </div>
            </div>
            <div className="flex-1">
              <h3 className="text-gray-900 mb-3" style={{ fontSize: '24px', fontWeight: 600 }}>
                Our Mission
              </h3>
              <p className="text-gray-600" style={{ fontSize: '16px' }}>
                In a world filled with sponsored content and biased reviews, we believe consumers deserve honest, data-driven product recommendations. Comparoo was built to cut through the noise and provide transparent comparisons you can trust.
              </p>
            </div>
          </div>
          
          {/* Transparency */}
          <div className="flex flex-col md:flex-row gap-8 items-start">
            <div className="flex-shrink-0">
              <div className="w-16 h-16 rounded-full bg-emerald-100 flex items-center justify-center">
                <Shield className="h-8 w-8 text-emerald-600" />
              </div>
            </div>
            <div className="flex-1">
              <h3 className="text-gray-900 mb-3" style={{ fontSize: '24px', fontWeight: 600 }}>
                Naturally Unbiased
              </h3>
              <p className="text-gray-600" style={{ fontSize: '16px' }}>
                We don't accept payment from manufacturers or brands to influence our rankings. Our AI analyzes publicly available data, customer reviews, and expert opinions to provide genuinely unbiased recommendations.
              </p>
            </div>
          </div>
          
          {/* Technology */}
          <div className="flex flex-col md:flex-row gap-8 items-start">
            <div className="flex-shrink-0">
              <div className="w-16 h-16 rounded-full bg-emerald-100 flex items-center justify-center">
                <Sparkles className="h-8 w-8 text-emerald-600" />
              </div>
            </div>
            <div className="flex-1">
              <h3 className="text-gray-900 mb-3" style={{ fontSize: '24px', fontWeight: 600 }}>
                Powered by AI
              </h3>
              <p className="text-gray-600" style={{ fontSize: '16px' }}>
                Our advanced AI technology continuously monitors and analyzes thousands of products across multiple categories. We process customer feedback, professional reviews, pricing data, and technical specifications to give you the complete picture.
              </p>
            </div>
          </div>
        </div>
        
        <div className="p-8 bg-gradient-to-br from-emerald-600 to-emerald-400 rounded-2xl text-white text-center">
          <h3 className="mb-4" style={{ fontSize: '24px', fontWeight: 600 }}>
            Join Our Community
          </h3>
          <p className="max-w-2xl mx-auto" style={{ fontSize: '16px' }}>
            We're constantly expanding our product database and improving our AI analysis. Have feedback or suggestions? We'd love to hear from you!
          </p>
        </div>
      </div>
      
      <Footer />
    </div>
  );
}
