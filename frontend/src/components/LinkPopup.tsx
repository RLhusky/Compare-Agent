"use client";

import { X, Copy, Check } from 'lucide-react';
import { useState } from 'react';

interface LinkPopupProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  link: string;
}

export function LinkPopup({ isOpen, onClose, title, link }: LinkPopupProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(link);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4"
        onClick={onClose}
      >
        {/* Modal */}
        <div
          className="bg-white rounded-2xl shadow-2xl max-w-md w-full p-6"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-black" style={{ fontSize: '20px', fontWeight: 600 }}>
              {title}
            </h3>
            <button
              onClick={onClose}
              className="p-2 rounded-xl hover:bg-gray-100 transition-all duration-300"
            >
              <X className="h-5 w-5 text-gray-700" />
            </button>
          </div>

          {/* Link Display */}
          <div className="mb-6">
            <div className="bg-gray-100 rounded-lg p-4 border border-gray-200">
              <p className="text-gray-700 break-all" style={{ fontSize: '14px' }}>
                {link}
              </p>
            </div>
          </div>

          {/* Copy Button */}
          <button
            onClick={handleCopy}
            className={`w-full py-3 rounded-xl transition-all duration-300 flex items-center justify-center gap-2 ${
              copied
                ? 'bg-green-600 text-white'
                : 'bg-emerald-600 text-white hover:bg-emerald-700'
            }`}
            style={{ fontSize: '16px', fontWeight: 600 }}
          >
            {copied ? (
              <>
                <Check className="h-5 w-5" />
                Copied!
              </>
            ) : (
              <>
                <Copy className="h-5 w-5" />
                Copy Link
              </>
            )}
          </button>
        </div>
      </div>
    </>
  );
}
