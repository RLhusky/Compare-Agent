"use client";

import { Star, ArrowRight, Check, X, ShoppingCart, ChevronLeft, ChevronRight, ArrowLeft } from 'lucide-react';
import { ImageWithFallback } from './figma/ImageWithFallback';
import { useState, useEffect, useCallback } from 'react';
import { Tag } from 'lucide-react';
import styles from './ProductCard.module.css';

interface Product {
  id: number;
  name: string;
  price: number;
  category: string;
  review: string;
}

interface ProductCardProps {
  product: Product;
  isVisible: boolean;
  allProducts?: Product[];
  currentIndex?: number;
  onNavigate?: (index: number) => void;
}

// Half Star Component
function HalfStar({ size = 'small' }: { size?: 'small' | 'large' }) {
  const sizeClass = size === 'small' ? styles.star : styles.starLarge;

  return (
    <div className={styles.halfStarWrapper} style={{ width: size === 'small' ? '16px' : '20px', height: size === 'small' ? '16px' : '20px' }}>
      <Star className={`${sizeClass} ${styles.starEmpty} ${styles.halfStarBackground}`} />
      <div className={styles.halfStarClip}>
        <Star className={`${sizeClass} ${styles.starFilled}`} />
      </div>
    </div>
  );
}

// Get category color - using design system
function getCategoryColor(category: string) {
  const colors: { [key: string]: { bg: string, text: string, border: string } } = {
    'Fashion': { bg: '#E1BEE7', text: '#6A1B9A', border: '#CE93D8' },
    'Accessories': { bg: '#BBDEFB', text: '#1565C0', border: '#90CAF9' },
    'Beauty': { bg: '#F8BBD0', text: '#C2185B', border: '#F48FB1' },
    'Home': { bg: '#FFE0B2', text: '#E65100', border: '#FFCC80' },
    'Jewelry': { bg: '#FFF9C4', text: '#F57F17', border: '#FFF59D' },
  };
  return colors[category] || { bg: '#E0E0E0', text: '#424242', border: '#BDBDBD' };
}

export function ProductCard({ product, isVisible, allProducts = [], currentIndex = 0, onNavigate }: ProductCardProps) {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [modalProductIndex, setModalProductIndex] = useState(currentIndex);

  // Update modal product index when currentIndex changes
  useEffect(() => {
    if (isModalOpen) {
      setModalProductIndex(currentIndex);
    }
  }, [currentIndex, isModalOpen]);

  // Get the current product to display in modal
  const modalProduct = allProducts.length > 0 ? allProducts[modalProductIndex] : product;

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

  // Generate consistent rating based on product ID (between 3.5 and 5)
  const getRating = (id: number) => {
    const seed = (id * 9301 + 49297) % 233280;
    const pseudoRandom = seed / 233280;
    return parseFloat((pseudoRandom * 1.5 + 3.5).toFixed(1));
  };

  const rating = getRating(product.id);

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
  const renderStars = (size: 'small' | 'large' = 'small', productId?: number) => {
    const ratingToUse = productId ? getRating(productId) : rating;
    const stars = [];
    const sizeClass = size === 'small' ? styles.star : styles.starLarge;

    for (let i = 1; i <= 5; i++) {
      if (i <= Math.floor(ratingToUse)) {
        stars.push(
          <Star key={i} className={`${sizeClass} ${styles.starFilled}`} />
        );
      } else if (i === Math.ceil(ratingToUse) && ratingToUse % 1 !== 0) {
        stars.push(
          <HalfStar key={i} size={size} />
        );
      } else {
        stars.push(
          <Star key={i} className={`${sizeClass} ${styles.starEmpty}`} />
        );
      }
    }
    return stars;
  };

  // Get first two sentences for preview
  const sentences = product.review.match(/[^.!?]+[.!?]+/g) || [];
  const firstTwoSentences = sentences.slice(0, 2).join(' ');

  const categoryStyle = getCategoryColor(product.category);

  return (
    <>
      <div className={`${styles.cardWrapper} ${isVisible ? styles.visible : ''}`}>
        <div className={styles.card}>
          {/* Image container */}
          <div className={styles.imageContainer} onClick={handleOpenModal}>
            <ImageWithFallback
              src={`https://images.unsplash.com/photo-${1500000000000 + product.id}?w=400&h=300&fit=crop`}
              alt={product.name}
              className={styles.image}
            />

            <div className={styles.imageOverlay} aria-hidden="true"></div>

            {/* Category badge */}
            <div
              className={styles.categoryBadge}
              style={{
                backgroundColor: categoryStyle.bg,
                color: categoryStyle.text,
                borderColor: categoryStyle.border
              }}
            >
              <Tag className={styles.categoryIcon} />
              {product.category}
            </div>
          </div>

          {/* Card content */}
          <div className={styles.content}>
            <div className={styles.header}>
              <h3 className={styles.title}>{product.name}</h3>
              <span className={styles.price}>${product.price}</span>
            </div>

            <div className={styles.description} onClick={handleOpenModal}>
              <p className={styles.descriptionText}>
                {firstTwoSentences}
              </p>
            </div>

            {/* Footer with button and stars */}
            <div className={styles.footer}>
              <button
                className={styles.viewButton}
                onClick={handleOpenModal}
                type="button"
                aria-label="View product details"
              >
                View Details
                <ArrowRight className={styles.buttonIcon} />
              </button>

              <div className={styles.rating} aria-label={`Rating: ${rating} out of 5 stars`}>
                {renderStars('small')}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Full Review Modal */}
      {isModalOpen && (
        <div className={styles.modal}>
          <div className={styles.modalContent}>
            {/* Back Button */}
            <div className={styles.backButtonWrapper}>
              <button
                onClick={() => setIsModalOpen(false)}
                className={styles.backButton}
                type="button"
                aria-label="Go back to products"
              >
                <ArrowLeft className={styles.backIcon} />
                Back
              </button>
            </div>

            {/* Main Content */}
            <div className={styles.modalMain}>
              {/* Top Section: Image Left, Title Right */}
              <div className={styles.modalGrid}>
                {/* Image */}
                <div>
                  <ImageWithFallback
                    src={`https://images.unsplash.com/photo-${1500000000000 + modalProduct.id}?w=1200&h=600&fit=crop`}
                    alt={modalProduct.name}
                    className={styles.modalImage}
                  />
                </div>

                {/* Details */}
                <div className={styles.modalDetails}>
                  <h1 className={styles.modalTitle}>{modalProduct.name}</h1>

                  {/* Stars */}
                  <div className={styles.modalRating}>
                    {renderStars('large', modalProduct.id)}
                    <span className={styles.ratingText}>{getRating(modalProduct.id)}/5.0</span>
                  </div>

                  {/* Price and Button */}
                  <div className={styles.priceRow}>
                    <span className={styles.modalPrice}>${modalProduct.price}</span>
                    <button
                      className={styles.shopButton}
                      type="button"
                      aria-label="View product on retailer site"
                    >
                      <ShoppingCart className={styles.shopIcon} />
                      View Product
                    </button>
                  </div>

                  {/* Overview */}
                  <div className={styles.overview}>
                    <h2 className={styles.sectionTitle}>About this Item:</h2>
                    <p className={styles.overviewText}>
                      {modalProduct.review}
                    </p>
                  </div>
                </div>
              </div>

              {/* Full Review */}
              <div className={styles.reviewSection}>
                <h2 className={styles.reviewTitle}>Full Review</h2>
                <p className={styles.reviewText}>
                  After extensive testing and user feedback analysis, we can confidently recommend this product
                  for its outstanding performance and reliability. The manufacturer has maintained high standards
                  in production, ensuring consistency and durability. Whether you're a first-time buyer or a
                  seasoned enthusiast, this product offers excellent value and satisfaction.
                </p>
                <p className={styles.reviewText}>
                  This comprehensive review covers all aspects of the product, including build quality,
                  design aesthetics, functionality, and overall value for money. Our expert reviewers have
                  tested this product extensively to provide you with the most accurate and helpful information
                  to make an informed decision.
                </p>
                <p className={styles.reviewText}>
                  The product demonstrates exceptional quality in its category and has received positive feedback
                  from numerous users. After comparing against multiple alternatives, this product stands out for
                  its combination of features, price point, and overall user satisfaction ratings.
                </p>
              </div>

              {/* Pros & Cons */}
              <div className={styles.prosConsGrid}>
                <div className={styles.prosBox}>
                  <h3 className={styles.listTitle}>Pros</h3>
                  <ul className={styles.list}>
                    <li className={styles.listItem}>
                      <Check className={`${styles.listIcon} ${styles.checkIcon}`} />
                      <span className={styles.listText}>Exceptional build quality and durability</span>
                    </li>
                    <li className={styles.listItem}>
                      <Check className={`${styles.listIcon} ${styles.checkIcon}`} />
                      <span className={styles.listText}>Great value for money</span>
                    </li>
                    <li className={styles.listItem}>
                      <Check className={`${styles.listIcon} ${styles.checkIcon}`} />
                      <span className={styles.listText}>Positive user reviews across the board</span>
                    </li>
                    <li className={styles.listItem}>
                      <Check className={`${styles.listIcon} ${styles.checkIcon}`} />
                      <span className={styles.listText}>Modern design that fits any style</span>
                    </li>
                  </ul>
                </div>

                <div className={styles.consBox}>
                  <h3 className={styles.listTitle}>Cons</h3>
                  <ul className={styles.list}>
                    <li className={styles.listItem}>
                      <X className={`${styles.listIcon} ${styles.xIcon}`} />
                      <span className={styles.listText}>Premium pricing may not suit all budgets</span>
                    </li>
                    <li className={styles.listItem}>
                      <X className={`${styles.listIcon} ${styles.xIcon}`} />
                      <span className={styles.listText}>Limited color options available</span>
                    </li>
                    <li className={styles.listItem}>
                      <X className={`${styles.listIcon} ${styles.xIcon}`} />
                      <span className={styles.listText}>Occasional stock shortages</span>
                    </li>
                  </ul>
                </div>
              </div>

              {/* Comparison Table */}
              <div className={styles.tableSection}>
                <h2 className={styles.reviewTitle}>Comparison to Alternatives</h2>
                <div className={styles.tableWrapper}>
                  <table className={styles.table}>
                    <thead className={styles.tableHead}>
                      <tr>
                        <th className={styles.tableHeaderCell}>Metric</th>
                        <th className={styles.tableHeaderCell}>Score</th>
                        <th className={styles.tableHeaderCell}>Industry Avg</th>
                        <th className={styles.tableHeaderCell}>Rating</th>
                      </tr>
                    </thead>
                    <tbody className={styles.tableBody}>
                      <tr className={styles.tableRow}>
                        <td className={styles.tableCell}>Build Quality</td>
                        <td className={styles.tableCell}>
                          <span className={styles.scoreBadge}>9.2/10</span>
                        </td>
                        <td className={styles.tableCell}>7.5/10</td>
                        <td className={styles.tableCell}>
                          <span className={styles.ratingBadge}>
                            <Check className={styles.badgeIcon} />
                            Excellent
                          </span>
                        </td>
                      </tr>
                      <tr className={styles.tableRow}>
                        <td className={styles.tableCell}>Value for Money</td>
                        <td className={styles.tableCell}>
                          <span className={styles.scoreBadge}>8.7/10</span>
                        </td>
                        <td className={styles.tableCell}>7.0/10</td>
                        <td className={styles.tableCell}>
                          <span className={styles.ratingBadge}>
                            <Check className={styles.badgeIcon} />
                            Great
                          </span>
                        </td>
                      </tr>
                      <tr className={styles.tableRow}>
                        <td className={styles.tableCell}>Design</td>
                        <td className={styles.tableCell}>
                          <span className={styles.scoreBadge}>9.5/10</span>
                        </td>
                        <td className={styles.tableCell}>8.0/10</td>
                        <td className={styles.tableCell}>
                          <span className={styles.ratingBadge}>
                            <Check className={styles.badgeIcon} />
                            Outstanding
                          </span>
                        </td>
                      </tr>
                      <tr className={styles.tableRow}>
                        <td className={styles.tableCell}>Durability</td>
                        <td className={styles.tableCell}>
                          <span className={styles.scoreBadge}>8.9/10</span>
                        </td>
                        <td className={styles.tableCell}>7.3/10</td>
                        <td className={styles.tableCell}>
                          <span className={styles.ratingBadge}>
                            <Check className={styles.badgeIcon} />
                            Excellent
                          </span>
                        </td>
                      </tr>
                      <tr className={styles.tableRow}>
                        <td className={styles.tableCell}>Customer Satisfaction</td>
                        <td className={styles.tableCell}>
                          <span className={styles.scoreBadge}>9.1/10</span>
                        </td>
                        <td className={styles.tableCell}>7.8/10</td>
                        <td className={styles.tableCell}>
                          <span className={styles.ratingBadge}>
                            <Check className={styles.badgeIcon} />
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
                <div className={styles.carousel}>
                  <h2 className={styles.carouselTitle}>More Products</h2>
                  <div className={styles.carouselWrapper}>
                    <div className={styles.carouselTrack} id={`product-carousel-${modalProductIndex}`}>
                      {allProducts.map((product, index) => (
                        <div
                          key={product.id}
                          onClick={() => {
                            setModalProductIndex(index);
                            if (onNavigate) onNavigate(index);
                            window.scrollTo({ top: 0, behavior: 'smooth' });
                          }}
                          className={`${styles.carouselCard} ${index === modalProductIndex ? styles.active : ''}`}
                        >
                          <div className={styles.carouselCardInner}>
                            <ImageWithFallback
                              src={`https://images.unsplash.com/photo-${1500000000000 + product.id}?w=400&h=300&fit=crop`}
                              alt={product.name}
                              className={styles.carouselImage}
                            />
                            <div className={styles.carouselCardContent}>
                              <p className={styles.carouselCardTitle}>{product.name}</p>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        const carousel = document.getElementById(`product-carousel-${modalProductIndex}`);
                        if (carousel) {
                          carousel.scrollBy({ left: -200, behavior: 'smooth' });
                        }
                      }}
                      className={`${styles.carouselButton} ${styles.carouselButtonLeft}`}
                      type="button"
                      aria-label="Scroll carousel left"
                    >
                      <ChevronLeft className={styles.carouselIcon} />
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        const carousel = document.getElementById(`product-carousel-${modalProductIndex}`);
                        if (carousel) {
                          carousel.scrollBy({ left: 200, behavior: 'smooth' });
                        }
                      }}
                      className={`${styles.carouselButton} ${styles.carouselButtonRight}`}
                      type="button"
                      aria-label="Scroll carousel right"
                    >
                      <ChevronRight className={styles.carouselIcon} />
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
