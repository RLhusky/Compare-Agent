"use client";

import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import type { ChangeEvent, FormEvent, MouseEvent, ReactNode } from 'react';
import { Search, SlidersHorizontal } from 'lucide-react';
import { Header } from './Header';
import { Footer } from './Footer';
import { SearchLoadingState } from './SearchLoadingState';
import { SearchProductCard } from './SearchProductCard';
import { FilterSidebar } from './FilterSidebar';
import { ErrorDisplay } from './ErrorDisplay';
import { 
  ApiError, 
  ComparisonResponse, 
  compareProducts, 
  generateSessionId, 
  connectProgressWebSocket,
  type ProgressUpdate 
} from '../lib/api';

type LoadingStatus = 'pending' | 'loading' | 'complete';

interface LoadingStepsState {
  scanning: LoadingStatus;
  analyzing: LoadingStatus;
  ranking: LoadingStatus;
  finalizing: LoadingStatus;
}

interface CardProduct {
  id: string;
  name: string;
  image: string;
  ratingValue: number;
  ratingText?: string;
  priceDisplay?: string;
  description: string;
  summary?: string;
  strengths: string[];
  weaknesses: string[];
  fullReview?: string;
  link?: string;
  label: 'Overall Pick' | null;
}

const DEFAULT_LOADING_STEPS: LoadingStepsState = {
  scanning: 'pending',
  analyzing: 'pending',
  ranking: 'pending',
  finalizing: 'pending',
};

interface SearchResultsPageProps {
  initialQuery: string;
}

export function SearchResultsPage({ initialQuery }: SearchResultsPageProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [displayedQuery, setDisplayedQuery] = useState(initialQuery);
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [loadingSteps, setLoadingSteps] = useState<LoadingStepsState>({
    ...DEFAULT_LOADING_STEPS,
    scanning: initialQuery.trim() ? 'loading' : 'pending',
  });
  const [progress, setProgress] = useState<number>(0);
  const [, setCurrentModalIndex] = useState<number>(0);
  const [comparisonData, setComparisonData] = useState<ComparisonResponse | null>(null);
  const [loading, setLoading] = useState(Boolean(initialQuery.trim()));
  const [error, setError] = useState<ApiError | Error | null>(null);

  const animationFrameRef = useRef<number | null>(null);
  const requestIdRef = useRef(0);
  const hasInitialLoadRef = useRef(false);

  const cancelProgressAnimation = useCallback(() => {
    if (animationFrameRef.current !== null) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
  }, []);

  const startProgressAnimation = useCallback(() => {
    cancelProgressAnimation();
    setProgress(5);

    const step = () => {
      let nextValue = 0;
      setProgress((prev: number) => {
        const increment = Math.max(0.5, (90 - prev) * 0.05);
        nextValue = Math.min(prev + increment, 90);
        return nextValue;
      });

      if (nextValue < 90) {
        animationFrameRef.current = requestAnimationFrame(step);
      } else {
        animationFrameRef.current = null;
      }
    };

    animationFrameRef.current = requestAnimationFrame(step);
  }, [cancelProgressAnimation]);

  const finishProgressAnimation = useCallback(() => {
    cancelProgressAnimation();
    setProgress(100);
  }, [cancelProgressAnimation]);

  useEffect(() => {
    return () => {
      cancelProgressAnimation();
    };
  }, [cancelProgressAnimation]);

  const parseRating = useCallback((value: string) => {
    const match = value.match(/[\d.]+/);
    if (!match) {
      return 0;
    }

    const parsed = parseFloat(match[0]);
    if (!Number.isFinite(parsed)) {
      return 0;
    }

    return Math.max(0, Math.min(parsed, 5));
  }, []);

  const executeSearch = useCallback(
    async (query: string) => {
      const trimmed = query.trim();
      if (!trimmed) {
        return;
      }

      const requestId = ++requestIdRef.current;
      const sessionId = generateSessionId();
      
      setSearchQuery('');
      setDisplayedQuery(trimmed);
      setCurrentModalIndex(0);
      setComparisonData(null);
      setError(null);
      setLoading(true);
      setLoadingSteps({
        scanning: 'loading',
        analyzing: 'pending',
        ranking: 'pending',
        finalizing: 'pending',
      });
      setProgress(0);

      // Simulate initial progress after 3 seconds
      const initialProgressTimer = setTimeout(() => {
        if (requestIdRef.current === requestId) {
          setProgress(15);
          setLoadingSteps(prev => ({
            ...prev,
            scanning: 'complete',
            analyzing: 'loading',
          }));
        }
      }, 3000);

      // Connect to WebSocket for real-time progress updates
      const cleanupWs = connectProgressWebSocket(sessionId, (update: ProgressUpdate) => {
        if (requestIdRef.current !== requestId) {
          return;
        }

        // Smooth progress update
        setProgress(prevProgress => {
          const targetProgress = update.progress;
          // If the new progress is significantly higher, transition smoothly
          if (targetProgress > prevProgress) {
            return targetProgress;
          }
          return prevProgress;
        });

        // Update loading steps based on progress
        if (update.step === 'discovery' && update.status === 'complete') {
          setLoadingSteps(prev => ({
            ...prev,
            scanning: 'complete',
            analyzing: 'loading',
          }));
        } else if (update.step === 'research' && update.status === 'complete') {
          setLoadingSteps(prev => ({
            ...prev,
            analyzing: 'complete',
            ranking: 'loading',
          }));
        } else if (update.step === 'comparison' && update.status === 'complete') {
          setLoadingSteps(prev => ({
            ...prev,
            ranking: 'complete',
            finalizing: 'loading',
          }));
          
          // Mark finalizing as complete 2 seconds after ranking
          setTimeout(() => {
            if (requestIdRef.current === requestId) {
              setLoadingSteps(prev => ({
                ...prev,
                finalizing: 'complete',
              }));
            }
          }, 2000);
        }
      });

      try {
        const response = await compareProducts(trimmed, undefined, sessionId);

        if (requestIdRef.current !== requestId) {
          clearTimeout(initialProgressTimer);
          return;
        }

        setComparisonData(response);
        setProgress(100);
        setLoadingSteps({
          scanning: 'complete',
          analyzing: 'complete',
          ranking: 'complete',
          finalizing: 'complete',
        });
      } catch (err) {
        clearTimeout(initialProgressTimer);
        
        if (requestIdRef.current !== requestId) {
          return;
        }

        const apiError =
          err instanceof ApiError
            ? err
            : new ApiError('Unexpected error while fetching comparison results.', {
                details: err,
              });

        setError(apiError);
        setLoadingSteps({
          ...DEFAULT_LOADING_STEPS,
          scanning: 'complete',
        });
      } finally {
        if (requestIdRef.current === requestId) {
          setLoading(false);
          cleanupWs();
          clearTimeout(initialProgressTimer);
        }
      }
    },
    []
  );

  useEffect(() => {
    if (initialQuery.trim() && !hasInitialLoadRef.current) {
      hasInitialLoadRef.current = true;
      executeSearch(initialQuery);
    } else if (!initialQuery.trim()) {
      setLoading(false);
      setLoadingSteps(DEFAULT_LOADING_STEPS);
    }
  }, [initialQuery, executeSearch]);

  const handleSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!searchQuery.trim() || loading) {
      return;
    }

    executeSearch(searchQuery);
  };

  const cardProducts: CardProduct[] = useMemo(() => {
    if (!comparisonData) {
      return [];
    }

    return comparisonData.products.map((product, index): CardProduct => ({
      id: product.product_id || String(index),
      name: product.name,
      image: product.image_url || '',
      ratingValue: parseRating(product.rating),
      ratingText: product.rating,
      priceDisplay: product.price_display || (product.price_cents ? `$${(product.price_cents / 100).toFixed(0)}` : '—'),
      description: product.description,
      summary: product.summary,
      strengths: product.strengths || [],
      weaknesses: product.weaknesses || [],
      fullReview: product.full_review,
      link: product.link,
      label: index === 0 ? 'Overall Pick' : null,
    }));
  }, [comparisonData, parseRating]);

  const shouldShowResults = !loading && !error && cardProducts.length > 0;
  const shouldShowLoading = loading;
  const shouldShowEmptyState = !loading && !error && comparisonData && cardProducts.length === 0;
  const shouldShowSearchBar = shouldShowResults || !!error || shouldShowEmptyState;

  const handleRetry = useCallback(() => {
    if (!displayedQuery.trim() || loading) {
      return;
    }
    executeSearch(displayedQuery);
  }, [displayedQuery, executeSearch, loading]);

  const errorDetails: ReactNode = useMemo(() => {
    if (!error) {
      return null;
    }

    if (error instanceof ApiError) {
      if (typeof error.details === 'string' && error.details.trim()) {
        return (
          <pre className="whitespace-pre-wrap break-words text-sm text-gray-600">
            {error.details}
          </pre>
        );
      }

      if (error.details && typeof error.details === 'object') {
        try {
          return (
            <pre className="whitespace-pre-wrap break-words text-sm text-gray-600">
              {JSON.stringify(error.details, null, 2)}
            </pre>
          );
        } catch (serializeError) {
          const message =
            serializeError instanceof Error
              ? serializeError.message
              : 'Unable to show additional details.';
          return (
            <span className="text-sm text-gray-600">
              {message}
            </span>
          );
        }
      }
    }

    if (displayedQuery.trim()) {
      return (
        <div className="space-y-1 text-sm text-gray-600">
          <p className="font-medium text-gray-700">Search query</p>
          <p>{displayedQuery}</p>
        </div>
      );
    }

    return null;
  }, [displayedQuery, error]);

  return (
    <div className="min-h-screen bg-white relative">
      <Header />
      
      <main className="max-w-6xl mx-auto px-4 py-8 pb-32">
        {/* Search Bar at Top - Centered - Only show when results are visible */}
        {shouldShowSearchBar && (
          <div className="mb-8 flex justify-center">
            <form onSubmit={handleSearch} className="relative flex gap-2 max-w-3xl w-full">
              <input
                type="text"
                value={searchQuery}
                onChange={(event: ChangeEvent<HTMLInputElement>) => setSearchQuery(event.target.value)}
                placeholder="Continue Comparing..."
                className="flex-1 px-6 py-4 pr-14 rounded-2xl border border-white/40 bg-white/80 backdrop-blur-xl focus:border-emerald-500 focus:outline-none shadow-lg"
                style={{ boxShadow: '0 8px 32px rgba(0, 0, 0, 0.1)' }}
              />
              <button
                type="submit"
                className="absolute right-16 top-1/2 -translate-y-1/2 p-3 text-white rounded-xl transition-colors"
                style={{ backgroundColor: '#52B54B' }}
                onMouseEnter={(event: MouseEvent<HTMLButtonElement>) => {
                  event.currentTarget.style.backgroundColor = '#469F40';
                }}
                onMouseLeave={(event: MouseEvent<HTMLButtonElement>) => {
                  event.currentTarget.style.backgroundColor = '#52B54B';
                }}
                disabled={loading}
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
        {shouldShowLoading && (
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

        {error && (
          <ErrorDisplay
            message={error.message}
            onRetry={loading ? undefined : handleRetry}
            details={errorDetails}
            retryLabel="Try Again"
          />
        )}

        {shouldShowEmptyState && (
          <div className="flex flex-col items-center justify-center min-h-[calc(100vh-200px)] -mt-8">
            <div className="text-center space-y-4">
              <h2 className="text-2xl font-semibold text-gray-800">No products found</h2>
              <p className="text-gray-600">
                We couldn&apos;t find any products for &quot;{displayedQuery}&quot;. Try a different search query.
              </p>
            </div>
          </div>
        )}

        {/* Results Grid */}
        {shouldShowResults && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mt-8 auto-rows-fr">
            {cardProducts.map((product, index) => (
              <SearchProductCard
                key={product.id}
                id={product.id}
                name={product.name}
                image={product.image}
                ratingValue={product.ratingValue}
                ratingText={product.ratingText}
                priceDisplay={product.priceDisplay}
                description={product.description}
                summary={product.summary}
                strengths={product.strengths}
                weaknesses={product.weaknesses}
                fullReview={product.fullReview}
                link={product.link}
                label={product.label}
                allProducts={cardProducts}
                currentIndex={index}
                onNavigate={setCurrentModalIndex}
                metricsTable={comparisonData?.comparison?.metrics_table}
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