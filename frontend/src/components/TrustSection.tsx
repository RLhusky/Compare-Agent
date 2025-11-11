import { CheckCircle, RefreshCw, Award } from 'lucide-react';

export function TrustSection() {
  return (
    <section className="py-10 bg-gray-50 border-y border-gray-200" style={{ minHeight: '80px' }}>
      <div className="max-w-6xl mx-auto px-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {/* Stat 1 */}
          <div className="flex flex-col items-center text-center">
            <div className="w-14 h-14 rounded-full bg-emerald-100 flex items-center justify-center mb-3">
              <CheckCircle className="h-7 w-7 text-emerald-600" />
            </div>
            <div className="text-gray-900 mb-1" style={{ fontSize: '24px', fontWeight: 700 }}>
              1000+ Products
            </div>
            <div className="text-gray-600" style={{ fontSize: '14px' }}>
              Analyzed & Compared
            </div>
          </div>
          
          {/* Stat 2 */}
          <div className="flex flex-col items-center text-center">
            <div className="w-14 h-14 rounded-full bg-blue-100 flex items-center justify-center mb-3">
              <RefreshCw className="h-7 w-7 text-blue-600" />
            </div>
            <div className="text-gray-900 mb-1" style={{ fontSize: '24px', fontWeight: 700 }}>
              Updated Daily
            </div>
            <div className="text-gray-600" style={{ fontSize: '14px' }}>
              Fresh pricing & data
            </div>
          </div>
          
          {/* Stat 3 */}
          <div className="flex flex-col items-center text-center">
            <div className="w-14 h-14 rounded-full bg-amber-100 flex items-center justify-center mb-3">
              <Award className="h-7 w-7 text-amber-600" />
            </div>
            <div className="text-gray-900 mb-1" style={{ fontSize: '24px', fontWeight: 700 }}>
              Naturally Unbiased
            </div>
            <div className="text-gray-600" style={{ fontSize: '14px' }}>
              No sponsored picks
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}