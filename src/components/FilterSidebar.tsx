"use client";

import { X } from 'lucide-react';
import { useEffect } from 'react';

interface FilterSidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

export function FilterSidebar({ isOpen, onClose }: FilterSidebarProps) {
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = 'unset';
    }
    
    return () => {
      document.body.style.overflow = 'unset';
    };
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/20 backdrop-blur-sm z-[9998]"
        onClick={onClose}
      />
      
      {/* Sidebar */}
      <div className="fixed top-0 right-0 h-screen w-80 backdrop-blur-2xl bg-white/80 border-l border-white/50 shadow-2xl z-[9999]">
        <div className="p-6 h-full overflow-y-auto relative z-10">
          {/* Header */}
          <div className="flex items-center justify-between mb-6">
            <h3 className="font-semibold" style={{ fontSize: '20px', color: '#4E342E' }}>Filters</h3>
            <button
              onClick={onClose}
              className="p-2 rounded-xl hover:bg-white/60 transition-all duration-300 border border-white/30"
            >
              <X className="h-5 w-5" style={{ color: '#4E342E' }} />
            </button>
          </div>
          
          {/* Filter Options */}
          <div className="space-y-6">
            {/* Category Filter */}
            <div>
              <h4 className="mb-3 font-semibold" style={{ color: '#4E342E' }}>Category</h4>
              <div className="space-y-2">
                {['Electronics', 'Fashion', 'Beauty', 'Home Decor', 'Jewelry', 'Accessories', 'Sports', 'Books', 'Kitchen', 'Toys'].map((category) => (
                  <label key={category} className="flex items-center gap-3 cursor-pointer group">
                    <input
                      type="checkbox"
                      className="w-4 h-4 rounded border-white/60 text-green-500 focus:ring-green-300"
                    />
                    <span className="transition-colors font-medium" style={{ color: '#4E342E' }}>
                      {category}
                    </span>
                  </label>
                ))}
              </div>
            </div>
            
            {/* Price Range Filter */}
            <div>
              <h4 className="mb-3 font-semibold" style={{ color: '#4E342E' }}>Price Range</h4>
              <div className="space-y-2">
                {['Under $25', '$25 - $50', '$50 - $75', '$75 - $100', '$100 - $150', 'Over $150'].map((range) => (
                  <label key={range} className="flex items-center gap-3 cursor-pointer group">
                    <input
                      type="checkbox"
                      className="w-4 h-4 rounded border-white/60 text-green-500 focus:ring-green-300"
                    />
                    <span className="transition-colors font-medium" style={{ color: '#4E342E' }}>
                      {range}
                    </span>
                  </label>
                ))}
              </div>
            </div>
          </div>
          
          {/* Apply Button */}
          <div className="mt-8">
            <button 
              onClick={onClose}
              className="w-full py-3 rounded-xl text-white transition-all duration-300 flex items-center justify-center font-semibold shadow-lg"
              style={{ backgroundColor: '#B4A585' }}
              onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#9B8F73'}
              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = '#B4A585'}
            >
              Apply Filters
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

