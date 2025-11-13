"use client";

import { useState } from 'react';
import Link from 'next/link';
import { LinkPopup } from './LinkPopup';

export function Header() {
  const [popupState, setPopupState] = useState<{
    isOpen: boolean;
    title: string;
    link: string;
  }>({
    isOpen: false,
    title: '',
    link: '',
  });

  const openContactPopup = () => {
    setPopupState({
      isOpen: true,
      title: 'Contact Us',
      link: 'nicholas.comparoo@gmail.com',
    });
  };

  const closePopup = () => {
    setPopupState({ isOpen: false, title: '', link: '' });
  };

  return (
    <header className="sticky top-0 z-50">
      <div className="w-full backdrop-blur-md border-b border-white/40 py-6 px-8" style={{ backgroundColor: '#FAF7F0', boxShadow: '0 4px 24px rgba(0, 0, 0, 0.04)' }}>
        <div className="max-w-7xl mx-auto flex items-center justify-between gap-4">
          {/* Kangaroo logo on the left */}
          <Link href="/" className="flex items-center cursor-pointer">
            <img src="/885c32b6b5c1d7631a690c5de5c363d2e8cc3f37.png" alt="Comparoo Logo" className="h-16 w-16 object-contain" />
          </Link>
          
          {/* Navigation in the middle */}
          <nav className="hidden md:flex items-center gap-6">
            <Link href="/how-it-works" className="px-4 py-2 transition-colors" style={{ color: '#000000' }}>
              How It Works
            </Link>
            <Link href="/" className="px-4 py-2 transition-colors" style={{ color: '#000000' }}>
              Home
            </Link>
            <Link href="/about" className="px-4 py-2 transition-colors" style={{ color: '#000000' }}>
              About
            </Link>
          </nav>
          
          {/* Contact Us on the right */}
          <div className="flex items-center gap-2">
            <button
              onClick={openContactPopup}
              className="px-4 py-2 transition-colors underline"
              style={{ color: '#000000', background: 'none', border: 'none', cursor: 'pointer', fontWeight: 'normal' }}
            >
              Contact Us
            </button>
          </div>
        </div>
      </div>

      {/* Link Popup */}
      <LinkPopup
        isOpen={popupState.isOpen}
        onClose={closePopup}
        title={popupState.title}
        link={popupState.link}
      />
    </header>
  );
}