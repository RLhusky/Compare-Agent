import { Header } from "./components/Header";
import { HeroSection } from "./components/HeroSection";
import { TrustSection } from "./components/TrustSection";
import { ProductGrid } from "./components/ProductGrid";
import { Footer } from "./components/Footer";
import { AboutPage } from "./components/AboutPage";
import { HowItWorksPage } from "./components/HowItWorksPage";
import { TermsOfServicePage } from "./components/TermsOfServicePage";
import { SearchResultsPage } from "./components/SearchResultsPage";
import { useState, useEffect } from "react";

export default function App() {
  const [currentPage, setCurrentPage] = useState<
    "home" | "about" | "how-it-works" | "terms" | "search"
  >("home");
  const [searchQuery, setSearchQuery] = useState("");

  // Expose navigation function globally - always available
  useEffect(() => {
    if (typeof window !== "undefined") {
      (window as any).navigateTo = (
        page:
          | "home"
          | "about"
          | "how-it-works"
          | "terms"
          | "search",
        query?: string,
      ) => {
        setCurrentPage(page);
        if (query) setSearchQuery(query);
        window.scrollTo(0, 0);
      };
    }
  }, []);

  if (currentPage === "about") {
    return <AboutPage />;
  }

  if (currentPage === "how-it-works") {
    return <HowItWorksPage />;
  }

  if (currentPage === "terms") {
    return <TermsOfServicePage />;
  }

  if (currentPage === "search") {
    return <SearchResultsPage initialQuery={searchQuery} />;
  }

  return (
    <div className="min-h-screen relative overflow-hidden bg-white">
      {/* Main content */}
      <div className="relative z-10">
        <Header />
        <HeroSection />
        <TrustSection />
        <main className="container mx-auto px-4 py-8">
          <ProductGrid />
        </main>
        <Footer />
      </div>
    </div>
  );
}