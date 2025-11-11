"use client";

import { Header } from "@/components/Header";
import { HeroSection } from "@/components/HeroSection";
import { TrustSection } from "@/components/TrustSection";
import { ProductGrid } from "@/components/ProductGrid";
import { Footer } from "@/components/Footer";

export default function Home() {
  return (
    <div className="min-h-screen relative overflow-hidden" style={{ backgroundColor: '#FAF7F0' }}>
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

