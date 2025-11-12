"use client";

import { Loader2, Check, Lightbulb } from 'lucide-react';
import { useEffect, useState, useRef } from 'react';

interface LoadingStepData {
  text: string;
  status: 'pending' | 'loading' | 'complete';
}

interface SearchLoadingStateProps {
  steps: LoadingStepData[];
  progress: number;
}

const SHOPPING_TIPS = [
  "Many comparison sites feature products that pay them commissions, not necessarily the best options.",
  "One review might miss issues that others catch. Cross-reference at least 2-3 trusted.",
  "A 2-year-old \"best pick\" might be outdated. Look for recently updated comparisons.",
  "Amazon's Choice badges are often based on sales velocity and Amazon's margins, not product quality.",
];

export function SearchLoadingState({ steps, progress }: SearchLoadingStateProps) {
  const [jumpOffset, setJumpOffset] = useState(0);
  const [currentTipIndex, setCurrentTipIndex] = useState(0);
  const [isTransitioning, setIsTransitioning] = useState(false);
  const progressBarRef = useRef<HTMLDivElement>(null);
  const lastProgressRef = useRef(0);

  // Smoother jumping kangaroo animation
  useEffect(() => {
    let up = true;
    const interval = setInterval(() => {
      setJumpOffset((prev) => {
        if (up) {
          if (prev >= 15) {
            up = false;
            return prev - 1.5;
          }
          return prev + 1.5;
        } else {
          if (prev <= 0) {
            up = true;
            return prev + 1.5;
          }
          return prev - 1.5;
        }
      });
    }, 50);
    return () => clearInterval(interval);
  }, []);

  // Shopping tips rotation
  useEffect(() => {
    const interval = setInterval(() => {
      setIsTransitioning(true);
      setTimeout(() => {
        setCurrentTipIndex((prev) => (prev + 1) % SHOPPING_TIPS.length);
        setIsTransitioning(false);
      }, 300);
    }, 4000); // Change tip every 4 seconds

    return () => clearInterval(interval);
  }, []);

  // Smooth progress bar update using direct DOM manipulation - no CSS transitions
  useEffect(() => {
    if (progressBarRef.current) {
      // Directly update the DOM element for buttery smooth animation
      // No CSS transition - JavaScript handles all animation
      progressBarRef.current.style.width = `${progress}%`;
      lastProgressRef.current = progress;
    }
  }, [progress]);

  return (
    <>
      <div className="bg-white rounded-2xl border border-gray-200 p-8 shadow-sm" style={{ minHeight: '280px' }}>
        {/* Header with Jumping Kangaroo */}
        <div className="flex items-center gap-4 mb-6">
          <div className="relative flex items-center justify-center w-14 h-14">
            <img 
              src="/885c32b6b5c1d7631a690c5de5c363d2e8cc3f37.png" 
              alt="Comparoo" 
              className="w-14 h-14 object-contain"
              style={{ transform: `translateY(-${jumpOffset}px)`, transition: 'transform 0.08s ease-out' }}
            />
          </div>
          <div>
            <h3 style={{ fontSize: '18px', fontWeight: 600, color: '#4E342E' }}>
              Finding the best options for you
            </h3>
            <p style={{ fontSize: '14px', color: '#4E342E' }}>
              This usually takes 15-20 seconds
            </p>
          </div>
        </div>

        {/* Progress Bar */}
        <div className="mb-6">
          <div className="w-full h-2.5 bg-gray-100 rounded-full overflow-hidden">
            <div 
              ref={progressBarRef}
              className="h-full rounded-full"
              style={{ 
                background: 'linear-gradient(to right, #B4A585, #9B8F73)',
                width: '0%',
                transition: 'width 0.5s ease-out',
                willChange: 'width',
                transform: 'translateZ(0)', // Force hardware acceleration
                backfaceVisibility: 'hidden'
              }}
            />
          </div>
        </div>

        {/* Loading Steps - Fixed height container */}
        <div className="space-y-3" style={{ minHeight: '140px' }}>
          {steps.map((step, index) => {
            // Always render all steps, show placeholder for pending
            if (step.status === 'pending') {
              return (
                <div key={index} className="flex items-center justify-between py-2 opacity-0" style={{ height: '36px' }}>
                  <span style={{ fontSize: '15px', color: '#000000' }}>
                    {step.text}
                  </span>
                  <div className="flex-shrink-0 ml-3 w-5 h-5" />
                </div>
              );
            }

            return (
              <div key={index} className="flex items-center justify-between py-2 opacity-100" style={{ height: '36px' }}>
                <span style={{ fontSize: '15px', color: '#4E342E' }}>
                  {step.text}
                </span>
                <div className="flex-shrink-0 ml-3">
                  {step.status === 'loading' && (
                    <Loader2 className="w-5 h-5 animate-spin" style={{ color: '#B4A585' }} />
                  )}
                  {step.status === 'complete' && (
                    <div className="w-5 h-5 rounded-sm flex items-center justify-center" style={{ backgroundColor: '#52B54B' }}>
                      <Check className="w-3.5 h-3.5 text-white" strokeWidth={3} />
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Shopping Tips Section */}
      <div className="mt-8 max-w-4xl mx-auto">
        <div className="bg-white/90 backdrop-blur-xl rounded-xl p-6 border border-gray-200 shadow-sm">
          <div className="flex items-start gap-4">
            <div className="flex-shrink-0 mt-1">
              <Lightbulb className="w-6 h-6" style={{ color: '#B4A585' }} />
            </div>
            <div className="flex-1 min-h-[60px] flex items-center">
              <p
                className={`transition-opacity duration-300 ${isTransitioning ? 'opacity-0' : 'opacity-100'}`}
                style={{ fontSize: '16px', lineHeight: '1.6', color: '#4E342E' }}
              >
                {SHOPPING_TIPS[currentTipIndex]}
              </p>
            </div>
          </div>
          {/* Progress dots */}
          <div className="flex gap-2 mt-5 justify-center">
            {SHOPPING_TIPS.map((_, index) => (
              <div
                key={index}
                className={`h-1.5 rounded-full transition-all duration-300 ${
                  index === currentTipIndex
                    ? 'w-8'
                    : 'w-1.5'
                }`}
                style={{
                  backgroundColor: index === currentTipIndex ? '#B4A585' : 'rgba(180, 165, 133, 0.4)',
                  height: '6px'
                }}
              />
            ))}
          </div>
        </div>
      </div>
    </>
  );
}