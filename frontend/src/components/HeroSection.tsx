"use client";

import { Send, SlidersHorizontal, Loader2 } from 'lucide-react';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { FilterSidebar } from './FilterSidebar';
import styles from './HeroSection.module.css';

export function HeroSection() {
  const router = useRouter();
  const [searchQuery, setSearchQuery] = useState('');
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [isSearching, setIsSearching] = useState(false);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!searchQuery.trim()) return;

    setIsSearching(true);

    // Simulate network delay for better UX feedback
    await new Promise(resolve => setTimeout(resolve, 300));

    // Navigate to search results page
    router.push(`/search?q=${encodeURIComponent(searchQuery)}`);

    // Reset searching state after navigation starts
    setIsSearching(false);
  };

  return (
    <section className={styles.hero}>
      {/* Gradient Background */}
      <div className={styles.gradient} aria-hidden="true"></div>

      {/* Geometric Pattern Overlay */}
      <div className={styles.pattern} aria-hidden="true">
        <div className={`${styles.patternShape} ${styles.patternCircle1}`}></div>
        <div className={`${styles.patternShape} ${styles.patternSquare1}`}></div>
        <div className={`${styles.patternShape} ${styles.patternSquare2}`}></div>
        <div className={`${styles.patternShape} ${styles.patternCircle2}`}></div>
      </div>

      {/* Content */}
      <div className={styles.content}>
        <h1 className={styles.heading}>
          Find the Best Products
        </h1>
        <p className={styles.subheading}>
          Unbiased AI-powered reviews to help you make informed decisions
        </p>

        {/* Search Bar */}
        <div className={styles.searchContainer}>
          <form onSubmit={handleSearch} className={styles.searchForm}>
            <div className={styles.searchWrapper}>
              <div className={styles.inputWrapper}>
                {/* Filter Button */}
                <button
                  type="button"
                  className={styles.filterButton}
                  onClick={() => setIsFilterOpen(!isFilterOpen)}
                  aria-label="Open filters"
                  disabled={isSearching}
                >
                  <SlidersHorizontal className={styles.icon} />
                </button>

                {/* Search Input */}
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search products to compare..."
                  className={styles.searchInput}
                  disabled={isSearching}
                  aria-label="Search products"
                />

                {/* Submit Button */}
                <button
                  type="submit"
                  className={`${styles.submitButton} ${isSearching ? styles.loading : ''}`}
                  disabled={isSearching || !searchQuery.trim()}
                  aria-label={isSearching ? 'Searching...' : 'Search'}
                >
                  {isSearching ? (
                    <Loader2 className={styles.icon} />
                  ) : (
                    <Send className={styles.icon} />
                  )}
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
