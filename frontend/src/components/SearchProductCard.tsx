"use client";

import { Star, ArrowRight, Check, X, ShoppingCart, ChevronLeft, ChevronRight, ArrowLeft } from 'lucide-react';
import { ImageWithFallback } from './figma/ImageWithFallback';
import { LinkPopup } from './LinkPopup';
import { useState, useEffect, useCallback } from 'react';

interface SearchProductCardProps {
  id: number;
  name: string;
  image: string;
  rating: number;
  price: string;
  description: string;
  label: 'Overall Pick' | null;
  allProducts?: Array<{
    id: number;
    name: string;
    image: string;
    rating: number;
    price: string;
    description: string;
    label: 'Overall Pick' | null;
  }>;
  currentIndex?: number;
  onNavigate?: (index: number) => void;
}

// Half Star Component
function HalfStar({ size = 'small' }: { size?: 'small' | 'large' }) {
  const sizeClass = size === 'small' ? 'h-4 w-4' : 'h-5 w-5';
  
  return (
    <div className="relative inline-block" style={{ width: size === 'small' ? '16px' : '20px', height: size === 'small' ? '16px' : '20px' }}>
      <Star className={`${sizeClass} absolute top-0 left-0 text-gray-300`} />
      <div className="absolute top-0 left-0 overflow-hidden" style={{ width: '50%', height: '100%' }}>
        <Star className={`${sizeClass}`} style={{ fill: '#FFD700', color: '#FFD700' }} />
      </div>
    </div>
  );
}

// Get label styling - black squircle for Overall Pick
function getLabelStyle(label: 'Overall Pick') {
  return {
    background: '#000000',
    color: '#FFFFFF',
    borderColor: '#000000',
    boxShadow: '0 2px 8px rgba(0, 0, 0, 0.3)'
  };
}

export function SearchProductCard({ id, name, image, rating, price, description, label, allProducts = [], currentIndex = 0, onNavigate }: SearchProductCardProps) {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isButtonHovered, setIsButtonHovered] = useState(false);
  const [isLinkPopupOpen, setIsLinkPopupOpen] = useState(false);
  const [modalProductIndex, setModalProductIndex] = useState(currentIndex);
  
  // Update modal product index when currentIndex changes
  useEffect(() => {
    if (isModalOpen) {
      setModalProductIndex(currentIndex);
    }
  }, [currentIndex, isModalOpen]);
  
  // Get the current product to display in modal
  const modalProduct = allProducts.length > 0 ? allProducts[modalProductIndex] : { id, name, image, rating, price, description, label };
  
  const handlePrevious = useCallback(() => {
    if (allProducts.length > 0) {
      setModalProductIndex((prevIndex) => {
        const newIndex = prevIndex > 0 ? prevIndex - 1 : allProducts.length - 1;
        if (onNavigate) onNavigate(newIndex);
        return newIndex;
      });
    }
  }, [allProducts.length, onNavigate]);
  
  const handleNext = useCallback(() => {
    if (allProducts.length > 0) {
      setModalProductIndex((prevIndex) => {
        const newIndex = prevIndex < allProducts.length - 1 ? prevIndex + 1 : 0;
        if (onNavigate) onNavigate(newIndex);
        return newIndex;
      });
    }
  }, [allProducts.length, onNavigate]);
  
  // Handle keyboard navigation
  useEffect(() => {
    if (!isModalOpen || allProducts.length <= 1) return;
    
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft') {
        e.preventDefault();
        handlePrevious();
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        handleNext();
      }
    };
    
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isModalOpen, allProducts.length, handlePrevious, handleNext]);
  
  const handleOpenModal = () => {
    setModalProductIndex(currentIndex);
    setIsModalOpen(true);
  };

  // Prevent body scroll when modal is open
  useEffect(() => {
    if (isModalOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = 'unset';
    }
    return () => {
      document.body.style.overflow = 'unset';
    };
  }, [isModalOpen]);

  // Close modal on Escape key press
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isModalOpen) {
        setIsModalOpen(false);
      }
    };
    
    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [isModalOpen]);

  // Render stars based on rating
  const renderStars = (size: 'small' | 'large' = 'small', productRating?: number) => {
    const ratingToUse = productRating !== undefined ? productRating : rating;
    const stars = [];
    const iconSize = size === 'small' ? 'h-4 w-4' : 'h-5 w-5';
    
    for (let i = 1; i <= 5; i++) {
      if (i <= Math.floor(ratingToUse)) {
        stars.push(
          <Star key={i} className={`${iconSize}`} style={{ fill: '#FFD700', color: '#FFD700' }} />
        );
      } else if (i === Math.ceil(ratingToUse) && ratingToUse % 1 !== 0) {
        stars.push(
          <HalfStar key={i} size={size} />
        );
      } else {
        stars.push(
          <Star key={i} className={`${iconSize} text-gray-300`} />
        );
      }
    }
    return stars;
  };

  return (
    <>
      <div className="group transition-all duration-500 transform">
        <div className="bg-white rounded-none border border-gray-200 hover:shadow-lg transition-all duration-300 overflow-hidden hover:-translate-y-2 h-full flex flex-col" style={{ boxShadow: '0 4px 6px rgba(0, 0, 0, 0.07)' }}>
          {/* Image container */}
          <div 
            className="relative aspect-[4/3] overflow-hidden bg-gradient-to-br from-gray-100 to-gray-200 cursor-pointer"
            onClick={() => setIsModalOpen(true)}
          >
            <ImageWithFallback
              src={image}
              alt={name}
              className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110"
            />
            
            {/* Gradient overlay at bottom */}
            <div className="absolute bottom-0 left-0 right-0 h-20 bg-gradient-to-t from-black/30 to-transparent"></div>
            
            {/* Label badge - top left */}
            {label && (
              <div className="absolute top-3 left-3">
                <span className="inline-flex items-center gap-1 px-3 py-1.5 border" style={{ 
                  fontSize: '12px', 
                  fontWeight: 600,
                  borderRadius: '4px',
                  background: getLabelStyle(label).background,
                  color: getLabelStyle(label).color,
                  borderColor: getLabelStyle(label).borderColor,
                  boxShadow: getLabelStyle(label).boxShadow
                }}>
                  {label}
                </span>
              </div>
            )}
          </div>
          
          {/* Product info */}
          <div className="p-6 flex-1 flex flex-col">
            <div className="flex items-start justify-between mb-3">
              <h3 className="flex-1" style={{ fontSize: '22px', fontWeight: 700, color: '#4E342E' }}>{name}</h3>
              <span className="ml-3 flex-shrink-0" style={{ fontSize: '18px', fontWeight: 700, color: '#52B54B' }}>{price}</span>
            </div>
            
            {/* Description - clickable */}
            <div 
              className="mb-5 cursor-pointer"
              onClick={handleOpenModal}
            >
              <p className="leading-relaxed transition-colors" style={{ fontSize: '15px', color: '#4E342E' }}>
                {description}
              </p>
            </div>
            
            {/* Bottom section with button and Stars */}
            <div className="flex items-center justify-between gap-4 pt-4 border-t border-gray-100 mt-auto">
              <button 
                className="inline-flex items-center gap-2 px-5 py-2.5 text-white transition-all duration-300 shadow-md hover:shadow-lg group/btn flex-shrink-0"
                style={{ borderRadius: '4px', backgroundColor: '#52B54B', fontSize: '14px', fontWeight: 600 }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = '#469F40';
                  setIsButtonHovered(true);
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = '#52B54B';
                  setIsButtonHovered(false);
                }}
                onClick={handleOpenModal}
              >
                View Details
                <ArrowRight className={`h-4 w-4 transition-transform duration-300 ${isButtonHovered ? 'translate-x-1' : ''}`} />
              </button>
              
              <div className="flex items-center gap-1 flex-shrink-0">
                {renderStars('small')}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Full Review Modal - Full Page Layout */}
      {isModalOpen && (
        <div 
          className="fixed inset-0 bg-white z-50 overflow-y-auto"
        >
          <div className="min-h-screen" style={{ backgroundColor: '#FAF7F0' }}>
            {/* Back Button - Top Left */}
            <div className="sticky top-0 z-10 p-6" style={{ backgroundColor: '#FAF7F0' }}>
              <button
                onClick={() => setIsModalOpen(false)}
                className="inline-flex items-center gap-2 px-4 py-2 transition-all duration-300"
                style={{ borderRadius: '4px', backgroundColor: '#B4A585', color: '#FFFFFF' }}
                onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#9B8F73'}
                onMouseLeave={(e) => e.currentTarget.style.backgroundColor = '#B4A585'}
              >
                <ArrowLeft className="h-5 w-5" />
                Back
              </button>
            </div>

            {/* Main Content */}
            <div className="max-w-7xl mx-auto px-6 pb-8">
              {/* Top Section: Image Left, Title Right */}
              <div className="grid md:grid-cols-2 gap-12 mb-8">
                {/* Image - Top Left */}
                <div className="w-full relative">
                  <ImageWithFallback
                    src={modalProduct.image}
                    alt={modalProduct.name}
                    className="w-full h-96 object-cover"
                    style={{ borderRadius: '4px' }}
                  />
                </div>

                {/* Title, Stars, Price, Button - Top Right */}
                <div className="flex flex-col">
                  <h1 className="mb-4" style={{ fontSize: '48px', fontWeight: 700, color: '#4E342E', lineHeight: '1.2' }}>{modalProduct.name}</h1>
                  
                  {/* Stars */}
                  <div className="flex items-center gap-2 mb-6">
                    {renderStars('large', modalProduct.rating)}
                    <span style={{ fontSize: '20px', color: '#4E342E' }}>{modalProduct.rating}/5.0</span>
                  </div>

                  {/* Price and View Product Button - Same Level */}
                  <div className="flex items-center justify-between mb-12">
                    <div className="flex items-baseline gap-1">
                      <span style={{ fontSize: '24px', fontWeight: 600, color: '#52B54B', opacity: 0.8 }}>$</span>
                      <span style={{ fontSize: '36px', fontWeight: 700, color: '#52B54B' }}>{modalProduct.price.replace('$', '')}</span>
                    </div>
                    <button 
                      onClick={(e) => {
                        e.stopPropagation();
                        setIsLinkPopupOpen(true);
                      }}
                      className="inline-flex items-center gap-2 px-6 py-3 text-white transition-all shadow-md"
                      style={{ borderRadius: '4px', backgroundColor: '#52B54B' }}
                      onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#469F40'}
                      onMouseLeave={(e) => e.currentTarget.style.backgroundColor = '#52B54B'}
                    >
                      <ShoppingCart className="h-5 w-5" />
                      View Product
                    </button>
                  </div>

                  {/* Overview Section */}
                  <div className="mb-8">
                    <h2 className="mb-3" style={{ fontSize: '24px', fontWeight: 600, color: '#4E342E' }}>About this Item:</h2>
                    <p style={{ fontSize: '18px', lineHeight: '1.8', color: '#4E342E' }}>
                      {modalProduct.description}
                    </p>
                  </div>
                </div>
              </div>

              {/* Full Review */}
              <div className="mb-8">
                <h2 className="mb-4 text-center" style={{ fontSize: '28px', fontWeight: 600, color: '#4E342E' }}>Full Review</h2>
                <p className="mb-4" style={{ fontSize: '17px', lineHeight: '1.7', color: '#4E342E' }}>
                  After extensive testing and user feedback analysis, we can confidently recommend this product
                  for its outstanding performance and reliability. The manufacturer has maintained high standards
                  in production, ensuring consistency and durability. Whether you&apos;re a first-time buyer or a
                  seasoned enthusiast, this product offers excellent value and satisfaction.
                </p>
                <p className="mb-4" style={{ fontSize: '17px', lineHeight: '1.7', color: '#4E342E' }}>
                  This comprehensive review covers all aspects of the product, including build quality,
                  design aesthetics, functionality, and overall value for money. Our expert reviewers have
                  tested this product extensively to provide you with the most accurate and helpful information
                  to make an informed decision.
                </p>
                <p style={{ fontSize: '17px', lineHeight: '1.7', color: '#4E342E' }}>
                  The product demonstrates exceptional quality in its category and has received positive feedback
                  from numerous users. After comparing against multiple alternatives, this product stands out for
                  its combination of features, price point, and overall user satisfaction ratings.
                  </p>
                </div>

              {/* Pros & Cons */}
              <div className="grid md:grid-cols-2 gap-6 mb-8">
                {/* Pros */}
                <div className="p-6" style={{ backgroundColor: '#D4EDDA', border: '1px solid #C3E6CB', borderRadius: '4px' }}>
                  <h3 className="mb-4" style={{ fontSize: '22px', fontWeight: 700, color: '#4E342E' }}>Pros</h3>
                  <ul className="space-y-3">
                    <li className="flex items-start gap-2" style={{ color: '#4E342E' }}>
                      <Check className="h-5 w-5 mt-0.5 flex-shrink-0" style={{ color: '#28A745' }} />
                      <span style={{ fontSize: '17px' }}>Exceptional build quality and durability</span>
                    </li>
                    <li className="flex items-start gap-2" style={{ color: '#4E342E' }}>
                      <Check className="h-5 w-5 mt-0.5 flex-shrink-0" style={{ color: '#28A745' }} />
                      <span style={{ fontSize: '17px' }}>Great value for money</span>
                    </li>
                    <li className="flex items-start gap-2" style={{ color: '#4E342E' }}>
                      <Check className="h-5 w-5 mt-0.5 flex-shrink-0" style={{ color: '#28A745' }} />
                      <span style={{ fontSize: '17px' }}>Positive user reviews across the board</span>
                    </li>
                    <li className="flex items-start gap-2" style={{ color: '#4E342E' }}>
                      <Check className="h-5 w-5 mt-0.5 flex-shrink-0" style={{ color: '#28A745' }} />
                      <span style={{ fontSize: '17px' }}>Modern design that fits any style</span>
                    </li>
                  </ul>
                </div>
                
                {/* Cons */}
                <div className="p-6" style={{ backgroundColor: '#F8D7DA', border: '1px solid #F5C6CB', borderRadius: '4px' }}>
                  <h3 className="mb-4" style={{ fontSize: '22px', fontWeight: 700, color: '#4E342E' }}>Cons</h3>
                  <ul className="space-y-3">
                    <li className="flex items-start gap-2" style={{ color: '#4E342E' }}>
                      <X className="h-5 w-5 mt-0.5 flex-shrink-0" style={{ color: '#DC3545' }} />
                      <span style={{ fontSize: '17px' }}>Higher price point compared to some competitors.</span>
                    </li>
                    <li className="flex items-start gap-2" style={{ color: '#4E342E' }}>
                      <X className="h-5 w-5 mt-0.5 flex-shrink-0" style={{ color: '#DC3545' }} />
                      <span style={{ fontSize: '17px' }}>Bulky design may not be ideal for all users.</span>
                    </li>
                  </ul>
                </div>
              </div>

              {/* Product Scorecard Table */}
              <div className="mb-8">
                <h2 className="mb-4 text-center" style={{ fontSize: '28px', fontWeight: 600, color: '#4E342E' }}>Comparison to Alternatives</h2>
                <div className="overflow-x-auto border border-gray-200" style={{ borderRadius: '4px' }}>
                  <table className="w-full">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-6 py-3 text-left" style={{ fontSize: '14px', fontWeight: 600, color: '#4E342E' }}>Metric</th>
                        <th className="px-6 py-3 text-left" style={{ fontSize: '14px', fontWeight: 600, color: '#4E342E' }}>Score</th>
                        <th className="px-6 py-3 text-left" style={{ fontSize: '14px', fontWeight: 600, color: '#4E342E' }}>Industry Avg</th>
                        <th className="px-6 py-3 text-left" style={{ fontSize: '14px', fontWeight: 600, color: '#4E342E' }}>Rating</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200">
                      <tr className="hover:bg-gray-50 transition-colors">
                        <td className="px-6 py-4" style={{ fontSize: '15px', color: '#4E342E' }}>Build Quality</td>
                        <td className="px-6 py-4">
                          <span className="inline-flex items-center px-2.5 py-1 bg-emerald-100 text-emerald-700" style={{ fontSize: '14px', fontWeight: 600, borderRadius: '4px' }}>
                            9.2/10
                          </span>
                        </td>
                        <td className="px-6 py-4" style={{ fontSize: '14px', color: '#4E342E' }}>7.5/10</td>
                        <td className="px-6 py-4">
                          <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-green-100 text-green-700" style={{ fontSize: '13px', fontWeight: 600, borderRadius: '4px' }}>
                            <Check className="h-3 w-3" />
                            Excellent
                          </span>
                        </td>
                      </tr>
                      <tr className="hover:bg-gray-50 transition-colors">
                        <td className="px-6 py-4" style={{ fontSize: '15px', color: '#4E342E' }}>Value for Money</td>
                        <td className="px-6 py-4">
                          <span className="inline-flex items-center px-2.5 py-1 bg-emerald-100 text-emerald-700" style={{ fontSize: '14px', fontWeight: 600, borderRadius: '4px' }}>
                            8.7/10
                          </span>
                        </td>
                        <td className="px-6 py-4" style={{ fontSize: '14px', color: '#4E342E' }}>7.0/10</td>
                        <td className="px-6 py-4">
                          <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-green-100 text-green-700" style={{ fontSize: '13px', fontWeight: 600, borderRadius: '4px' }}>
                            <Check className="h-3 w-3" />
                            Great
                          </span>
                        </td>
                      </tr>
                      <tr className="hover:bg-gray-50 transition-colors">
                        <td className="px-6 py-4" style={{ fontSize: '15px', color: '#4E342E' }}>Design</td>
                        <td className="px-6 py-4">
                          <span className="inline-flex items-center px-2.5 py-1 bg-emerald-100 text-emerald-700" style={{ fontSize: '14px', fontWeight: 600, borderRadius: '4px' }}>
                            9.5/10
                          </span>
                        </td>
                        <td className="px-6 py-4" style={{ fontSize: '14px', color: '#4E342E' }}>8.0/10</td>
                        <td className="px-6 py-4">
                          <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-green-100 text-green-700" style={{ fontSize: '13px', fontWeight: 600, borderRadius: '4px' }}>
                            <Check className="h-3 w-3" />
                            Outstanding
                          </span>
                        </td>
                      </tr>
                      <tr className="hover:bg-gray-50 transition-colors">
                        <td className="px-6 py-4" style={{ fontSize: '15px', color: '#4E342E' }}>Durability</td>
                        <td className="px-6 py-4">
                          <span className="inline-flex items-center px-2.5 py-1 bg-emerald-100 text-emerald-700" style={{ fontSize: '14px', fontWeight: 600, borderRadius: '4px' }}>
                            8.9/10
                          </span>
                        </td>
                        <td className="px-6 py-4" style={{ fontSize: '14px', color: '#4E342E' }}>7.3/10</td>
                        <td className="px-6 py-4">
                          <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-green-100 text-green-700" style={{ fontSize: '13px', fontWeight: 600, borderRadius: '4px' }}>
                            <Check className="h-3 w-3" />
                            Excellent
                          </span>
                        </td>
                      </tr>
                      <tr className="hover:bg-gray-50 transition-colors">
                        <td className="px-6 py-4" style={{ fontSize: '15px', color: '#4E342E' }}>Customer Satisfaction</td>
                        <td className="px-6 py-4">
                          <span className="inline-flex items-center px-2.5 py-1 bg-emerald-100 text-emerald-700" style={{ fontSize: '14px', fontWeight: 600, borderRadius: '4px' }}>
                            9.1/10
                          </span>
                        </td>
                        <td className="px-6 py-4" style={{ fontSize: '14px', color: '#4E342E' }}>7.8/10</td>
                        <td className="px-6 py-4">
                          <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-green-100 text-green-700" style={{ fontSize: '13px', fontWeight: 600, borderRadius: '4px' }}>
                            <Check className="h-3 w-3" />
                            Excellent
                          </span>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
              
              {/* Mini Card Carousel */}
              {allProducts.length > 1 && (
                <div className="mt-12">
                  <h2 className="mb-6" style={{ fontSize: '24px', fontWeight: 600, color: '#4E342E' }}>More Products</h2>
                  <div className="relative">
                    <div className="flex gap-4 overflow-x-auto pb-4 scrollbar-hide" style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }} id={`search-product-carousel-${modalProductIndex}`}>
                      {allProducts.map((product, index) => (
                        <div
                          key={product.id}
                          onClick={() => {
                            setModalProductIndex(index);
                            if (onNavigate) onNavigate(index);
                            window.scrollTo({ top: 0, behavior: 'smooth' });
                          }}
                          className={`flex-shrink-0 w-48 cursor-pointer transition-all ${
                            index === modalProductIndex ? 'ring-2 ring-green-500' : ''
                          }`}
                          style={{ borderRadius: '4px', overflow: 'hidden' }}
                        >
                          <div className="bg-white border border-gray-200 hover:shadow-lg transition-all">
                            <ImageWithFallback
                              src={product.image}
                              alt={product.name}
                              className="w-full h-32 object-cover"
                            />
                            <div className="p-3">
                              <p className="text-sm font-semibold" style={{ color: '#4E342E' }}>{product.name}</p>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
      
      {/* Link Popup for View Product */}
      <LinkPopup
        isOpen={isLinkPopupOpen}
        onClose={() => setIsLinkPopupOpen(false)}
        title="Product Link"
        link="https://example.com/product-link"
      />
    </>
  );
}