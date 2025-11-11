"use client";

import { useState, useEffect } from 'react';
import { Search, SlidersHorizontal } from 'lucide-react';
import { Header } from './Header';
import { Footer } from './Footer';
import { SearchLoadingState } from './SearchLoadingState';
import { SearchProductCard } from './SearchProductCard';
import { FilterSidebar } from './FilterSidebar';

interface SearchResultsPageProps {
  initialQuery: string;
}

export function SearchResultsPage({ initialQuery }: SearchResultsPageProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [displayedQuery, setDisplayedQuery] = useState(initialQuery);
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [loadingSteps, setLoadingSteps] = useState<{
    scanning: 'pending' | 'loading' | 'complete';
    analyzing: 'pending' | 'loading' | 'complete';
    ranking: 'pending' | 'loading' | 'complete';
    finalizing: 'pending' | 'loading' | 'complete';
  }>({
    scanning: 'loading',
    analyzing: 'pending',
    ranking: 'pending',
    finalizing: 'pending',
  });
  const [showResults, setShowResults] = useState(false);
  const [progress, setProgress] = useState(0);
  const [currentModalIndex, setCurrentModalIndex] = useState(0);

  // Mock products data - in real app this would come from backend
  const products = [
    {
      id: 1,
      name: 'Sony WH-1000XM5',
      image: 'https://images.unsplash.com/photo-1546435770-a3e426bf472b?w=400',
      rating: 4.8,
      price: '$399',
      description: 'Industry-leading noise cancellation with exceptional sound quality and all-day comfort.',
      label: 'Overall Pick' as const,
    },
    {
      id: 2,
      name: 'Anker Soundcore Q30',
      image: 'https://images.unsplash.com/photo-1484704849700-f032a568e944?w=400',
      rating: 4.5,
      price: '$79',
      description: 'Budget-friendly option with impressive noise cancellation and 40-hour battery life.',
      label: null,
    },
    {
      id: 3,
      name: 'Bose QuietComfort Ultra',
      image: 'https://images.unsplash.com/photo-1545127398-14699f92334b?w=400',
      rating: 4.7,
      price: '$429',
      description: 'Premium spatial audio with CustomTune technology for personalized sound.',
      label: null,
    },
    {
      id: 4,
      name: 'Sennheiser Momentum 4',
      image: 'https://images.unsplash.com/photo-1487215078519-e21cc028cb29?w=400',
      rating: 4.6,
      price: '$349',
      description: 'Audiophile-grade sound with adaptive noise cancellation and 60-hour battery.',
      label: null,
    },
    {
      id: 5,
      name: 'Apple AirPods Max',
      image: 'https://images.unsplash.com/photo-1606841837239-c5a1a4a07af7?w=400',
      rating: 4.4,
      price: '$549',
      description: 'Seamless Apple ecosystem integration with computational audio.',
      label: null,
    },
    {
      id: 6,
      name: 'JBL Tune 760NC',
      image: 'https://images.unsplash.com/photo-1577174881658-0f30157f72fd?w=400',
      rating: 4.3,
      price: '$129',
      description: 'Great everyday headphones with active noise cancellation and JBL Pure Bass.',
      label: null,
    },
  ];

  // Smooth continuous progress bar - updates every frame for buttery smooth animation
  useEffect(() => {
    const timers: NodeJS.Timeout[] = [];
    let animationFrameId: number;
    const startTime = performance.now();
    const duration = 10000; // 10 seconds total
    
    const animate = (currentTime: number) => {
      const elapsed = currentTime - startTime;
      const progressPercent = Math.min((elapsed / duration) * 100, 100);
      
      // Update progress on every frame for maximum smoothness
      setProgress(progressPercent);
      
      if (progressPercent < 100) {
        animationFrameId = requestAnimationFrame(animate);
      } else {
        setProgress(100);
      }
    };
    
    animationFrameId = requestAnimationFrame(animate);
    
    // Mark checkpoints as complete at specific times
    // Checkpoint 1: Complete scanning at 25% (after ~2.5 seconds)
    timers.push(setTimeout(() => {
      setLoadingSteps(prev => ({ ...prev, scanning: 'complete', analyzing: 'loading' }));
    }, 2500));
    
    // Checkpoint 2: Complete analyzing at 50% (after ~5 seconds total)
    timers.push(setTimeout(() => {
      setLoadingSteps(prev => ({ ...prev, analyzing: 'complete', ranking: 'loading' }));
    }, 5000));
    
    // Checkpoint 3: Complete ranking at 75% (after ~7.5 seconds total)
    timers.push(setTimeout(() => {
      setLoadingSteps(prev => ({ ...prev, ranking: 'complete', finalizing: 'loading' }));
    }, 7500));
    
    // Checkpoint 4: Complete finalizing at 100% (after ~10 seconds total)
    timers.push(setTimeout(() => {
      setLoadingSteps(prev => ({ ...prev, finalizing: 'complete' }));
      setShowResults(true);
      if (animationFrameId) {
        cancelAnimationFrame(animationFrameId);
      }
    }, 10000));

    return () => {
      timers.forEach(timer => clearTimeout(timer));
      if (animationFrameId) {
        cancelAnimationFrame(animationFrameId);
      }
    };
  }, []);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    
    // Update displayed query and clear input
    setDisplayedQuery(searchQuery);
    setSearchQuery('');
    
    // Reset and restart search
    setShowResults(false);
    setLoadingSteps({
      scanning: 'loading',
      analyzing: 'pending',
      ranking: 'pending',
      finalizing: 'pending',
    });
    setProgress(0);
    
    // Restart loading sequence with smooth continuous progress
    const timers: NodeJS.Timeout[] = [];
    let animationFrameId: number;
    const startTime = performance.now();
    const duration = 10000; // 10 seconds total
    
    const animate = (currentTime: number) => {
      const elapsed = currentTime - startTime;
      const progressPercent = Math.min((elapsed / duration) * 100, 100);
      
      // Update progress on every frame for maximum smoothness
      setProgress(progressPercent);
      
      if (progressPercent < 100) {
        animationFrameId = requestAnimationFrame(animate);
      } else {
        setProgress(100);
      }
    };
    
    animationFrameId = requestAnimationFrame(animate);
    
    // Mark checkpoints as complete at specific times
    // Checkpoint 1: Complete scanning at 25% (after ~2.5 seconds)
    timers.push(setTimeout(() => {
      setLoadingSteps(prev => ({ ...prev, scanning: 'complete', analyzing: 'loading' }));
    }, 2500));
    
    // Checkpoint 2: Complete analyzing at 50% (after ~5 seconds total)
    timers.push(setTimeout(() => {
      setLoadingSteps(prev => ({ ...prev, analyzing: 'complete', ranking: 'loading' }));
    }, 5000));
    
    // Checkpoint 3: Complete ranking at 75% (after ~7.5 seconds total)
    timers.push(setTimeout(() => {
      setLoadingSteps(prev => ({ ...prev, ranking: 'complete', finalizing: 'loading' }));
    }, 7500));
    
    // Checkpoint 4: Complete finalizing at 100% (after ~10 seconds total)
    timers.push(setTimeout(() => {
      setLoadingSteps(prev => ({ ...prev, finalizing: 'complete' }));
      setShowResults(true);
      if (animationFrameId) {
        cancelAnimationFrame(animationFrameId);
      }
    }, 10000));

    return () => {
      timers.forEach(timer => clearTimeout(timer));
      if (animationFrameId) {
        cancelAnimationFrame(animationFrameId);
      }
    };
  };

  return (
    <div className="min-h-screen bg-white relative">
      <Header />
      
      <main className="max-w-6xl mx-auto px-4 py-8 pb-32">
        {/* Search Bar at Top - Centered - Only show when results are visible */}
        {showResults && (
          <div className="mb-8 flex justify-center">
            <form onSubmit={handleSearch} className="relative flex gap-2 max-w-3xl w-full">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Continue Comparing..."
                className="flex-1 px-6 py-4 pr-14 rounded-2xl border border-white/40 bg-white/80 backdrop-blur-xl focus:border-emerald-500 focus:outline-none shadow-lg"
                style={{ boxShadow: '0 8px 32px rgba(0, 0, 0, 0.1)' }}
              />
              <button
                type="submit"
                              className="absolute right-16 top-1/2 -translate-y-1/2 p-3 text-white rounded-xl transition-colors"
                              style={{ backgroundColor: '#52B54B' }}
                              onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#469F40'}
                              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = '#52B54B'}
              >
                <Search className="w-5 h-5" />
              </button>
              
              {/* Filter Button */}
              <button
                type="button"
                className="px-4 rounded-2xl bg-white/80 backdrop-blur-xl hover:bg-white/90 transition-all shadow-lg border border-white/40 flex items-center gap-2"
                onClick={() => setIsFilterOpen(!isFilterOpen)}
              >
                <SlidersHorizontal className="h-5 w-5 text-gray-700" />
              </button>
            </form>
          </div>
        )}

        {/* Loading Steps */}
        {!showResults && (
          <div className="flex flex-col items-center justify-center min-h-[calc(100vh-200px)] -mt-8">
            <div className="max-w-4xl mx-auto w-full">
              <SearchLoadingState 
                steps={[
                  { text: 'Scanning 20+ expert reviews...', status: loadingSteps.scanning },
                  { text: 'Analyzing product specs...', status: loadingSteps.analyzing },
                  { text: 'Ranking top picks...', status: loadingSteps.ranking },
                  { text: 'Finalizing results...', status: loadingSteps.finalizing },
                ]}
                progress={progress}
              />
            </div>
          </div>
        )}

                    {/* Results Grid */}
                    {showResults && (
                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mt-8 auto-rows-fr">
                        {products.map((product, index) => (
                          <SearchProductCard
                            key={product.id}
                            id={product.id}
                            name={product.name}
                            image={product.image}
                            rating={product.rating}
                            price={product.price}
                            description={product.description}
                            label={product.label}
                            allProducts={products}
                            currentIndex={index}
                            onNavigate={setCurrentModalIndex}
                          />
                        ))}
                      </div>
                    )}
      </main>

      {/* Filter Sidebar */}
      <FilterSidebar isOpen={isFilterOpen} onClose={() => setIsFilterOpen(false)} />

      <Footer />
    </div>
  );
}