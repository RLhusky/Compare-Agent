"use client";

import { ProductCard } from './ProductCard';
import { useEffect, useState } from 'react';

const products = [
  { id: 1, name: 'Summer Breeze', price: 49.99, category: 'Fashion', review: 'This product exceeded all expectations with its quality and design. The attention to detail is remarkable and the value for money is outstanding.' },
  { id: 2, name: 'Cloud Nine', price: 79.99, category: 'Accessories', review: 'An exceptional accessory that combines style and functionality perfectly. The build quality is superior and it looks even better in person.' },
  { id: 3, name: 'Pink Dreams', price: 59.99, category: 'Beauty', review: 'A game-changing beauty product that delivers on all its promises. The formula is gentle yet effective and the results are visible within days.' },
  { id: 4, name: 'Sky High', price: 89.99, category: 'Fashion', review: 'Premium fashion piece that stands out from the crowd. The craftsmanship is impeccable and the fit is absolutely perfect for everyday wear.' },
  { id: 5, name: 'Ocean Mist', price: 39.99, category: 'Home', review: 'A wonderful addition to any home with its elegant design. It brings a sense of calm and sophistication to any space you place it in.' },
  { id: 6, name: 'Golden Hour', price: 99.99, category: 'Jewelry', review: 'Stunning jewelry that catches the light beautifully. The quality is exceptional and it makes a perfect statement piece for any occasion.' },
  { id: 7, name: 'Mint Fresh', price: 44.99, category: 'Beauty', review: 'Refreshing beauty product with natural ingredients. It leaves your skin feeling rejuvenated and has a pleasant, subtle scent that lasts.' },
  { id: 8, name: 'Lavender Fields', price: 54.99, category: 'Home', review: 'Creates a peaceful atmosphere in any room instantly. The quality is excellent and it serves both functional and decorative purposes beautifully.' },
  { id: 9, name: 'Sunset Glow', price: 69.99, category: 'Fashion', review: 'Beautiful fashion item with vibrant colors that stay true. The material is high-quality and durable, making it a worthwhile investment.' },
  { id: 10, name: 'Crystal Clear', price: 74.99, category: 'Accessories', review: 'Sleek and modern accessory with crystal clear quality. It complements any style and the durability ensures it will last for years.' },
  { id: 11, name: 'Rose Garden', price: 64.99, category: 'Beauty', review: 'Luxurious beauty product with a delicate floral scent. The formula is rich and nourishing, providing excellent results with regular use.' },
  { id: 12, name: 'Starlight', price: 84.99, category: 'Jewelry', review: 'Exquisite jewelry piece that sparkles like the night sky. The design is timeless and the craftsmanship is evident in every detail.' },
];

export function ProductGrid() {
  const [visibleProducts, setVisibleProducts] = useState<number[]>([]);
  const [currentModalIndex, setCurrentModalIndex] = useState(0);
  
  useEffect(() => {
    const timeouts: NodeJS.Timeout[] = [];
    
    // Stagger the animation of products appearing
    products.forEach((_, index) => {
      const timeout = setTimeout(() => {
        setVisibleProducts(prev => [...prev, index]);
      }, index * 100);
      timeouts.push(timeout);
    });
    
    // Cleanup function to clear all timeouts
    return () => {
      timeouts.forEach(timeout => clearTimeout(timeout));
    };
  }, []);

  return (
    <section className="py-8 relative">
      {/* Centered bar with title */}
      <div className="mb-8 flex justify-center">
        <div className="w-full max-w-2xl backdrop-blur-md bg-white/40 rounded-2xl border border-white/50 shadow-lg shadow-gray-200/50 px-6 py-3 text-center">
          <h2 style={{ color: '#4E342E' }}>Best Picks of 2025</h2>
        </div>
      </div>
      
      {/* 3 columns wide x 4 rows grid with increased spacing */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8 auto-rows-fr">
        {products.map((product, index) => (
          <ProductCard
            key={product.id}
            product={product}
            isVisible={visibleProducts.includes(index)}
            allProducts={products}
            currentIndex={index}
            onNavigate={setCurrentModalIndex}
          />
        ))}
      </div>
    </section>
  );
}