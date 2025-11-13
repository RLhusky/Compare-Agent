"use client";

import { Send, SlidersHorizontal } from 'lucide-react';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { FilterSidebar } from './FilterSidebar';

export function HeroSection() {
  const router = useRouter();
  const [searchQuery, setSearchQuery] = useState('');
  const [isFilterOpen, setIsFilterOpen] = useState(false);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      // Navigate to search results page
      router.push(`/search?q=${encodeURIComponent(searchQuery)}`);
    }
  };

  return (
    <section className="relative overflow-hidden" style={{ height: '550px' }}>
      {/* Emerald Gradient Background - more trustworthy than neon green */}
      <div className="absolute inset-0 bg-gradient-to-br from-emerald-600 to-emerald-400"></div>
      
      {/* Geometric Pattern Overlay */}
      <div className="absolute inset-0 opacity-10">
        <div className="absolute top-10 left-10 w-32 h-32 border-4 border-white rounded-full"></div>
        <div className="absolute bottom-20 right-20 w-40 h-40 border-4 border-white rotate-45"></div>
        <div className="absolute top-40 right-40 w-24 h-24 border-4 border-white"></div>
        <div className="absolute bottom-40 left-40 w-28 h-28 border-4 border-white rounded-full"></div>
      </div>
      
      {/* Content */}
      <div className="relative z-10 flex flex-col items-center justify-center h-full px-4">
        <h1 className="text-white mb-4 text-center" style={{ fontSize: '56px', fontWeight: 800 }}>
          Find the Best Products
        </h1>
        <p className="text-white/90 mb-8 text-center max-w-2xl" style={{ fontSize: '20px', opacity: 0.9 }}>
          Unbiased AI-powered reviews to help you make informed decisions
        </p>
        
                    {/* Large Search Bar with enhanced focus state */}
                    <div className="w-full max-w-3xl relative">
                      <form onSubmit={handleSearch}>
                        <div className="relative flex gap-2">
                          <div className="relative flex-1">
                            <button
                              type="button"
                              className="absolute left-5 top-1/2 transform -translate-y-1/2 p-2 rounded-xl transition-all flex items-center justify-center hover:bg-white/60"
                              style={{ width: '40px', height: '40px' }}
                              onClick={() => setIsFilterOpen(!isFilterOpen)}
                            >
                              <SlidersHorizontal className="h-4 w-4" style={{ color: '#4E342E' }} />
                            </button>
                            <input
                              type="text"
                              value={searchQuery}
                              onChange={(e) => setSearchQuery(e.target.value)}
                              placeholder="Search products to compare..."
                              className="w-full pl-16 pr-14 rounded-2xl placeholder:text-gray-400 focus:outline-none focus:ring-4 border-2 transition-all shadow-lg"
                              style={{ 
                                height: '56px', 
                                fontSize: '16px', 
                                backgroundColor: '#FAF7F0',
                                color: '#4E342E',
                                borderColor: 'rgba(180, 165, 133, 0.3)',
                                boxShadow: '0 2px 8px rgba(0, 0, 0, 0.06)' 
                              }}
                            />
                            {/* Send Button */}
                            <button
                              type="submit"
                              className="absolute right-2 top-1/2 transform -translate-y-1/2 p-2 rounded-xl text-white transition-all flex items-center justify-center"
                              style={{ backgroundColor: '#52B54B', width: '40px', height: '40px' }}
                              onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#469F40'}
                              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = '#52B54B'}
                            >
                              <Send className="h-4 w-4 text-white" />
                            </button>
                          </div>
                        </div>
                      </form>
                    </div>
      </div>
      
      {/* Filter Sidebar */}
      <FilterSidebar isOpen={isFilterOpen} onClose={() => setIsFilterOpen(false)} />
    </section>
  );
}