"use client";

import { Twitter, Instagram, Youtube } from 'lucide-react';
import { useState } from 'react';
import Link from 'next/link';
import { LinkPopup } from './LinkPopup';

export function Footer() {
  const [popupState, setPopupState] = useState<{
    isOpen: boolean;
    title: string;
    link: string;
  }>({
    isOpen: false,
    title: '',
    link: '',
  });

  const openPopup = (title: string, link: string) => {
    setPopupState({ isOpen: true, title, link });
  };

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
    <footer className="mt-16" style={{ backgroundColor: '#6B5D4F' }}>
      <div className="max-w-7xl mx-auto px-4 py-12">
        <div className="flex flex-col md:flex-row md:justify-between md:items-start gap-12 mb-8">
          {/* Company - centered on mobile, middle on desktop */}
          <div className="text-center md:text-center md:flex-1 md:flex md:justify-center">
            <div>
              <h3 className="mb-4" style={{ fontSize: '16px', fontWeight: 600, color: '#FAF7F0' }}>Company</h3>
              <ul className="space-y-2">
                <li>
                  <Link 
                    href="/about"
                    className="transition-colors text-sm"
                    style={{ color: '#FAF7F0' }} 
                  >
                    About
                  </Link>
                </li>
                <li>
                  <Link 
                    href="/how-it-works"
                    className="transition-colors text-sm"
                    style={{ color: '#FAF7F0' }} 
                  >
                    How It Works
                  </Link>
                </li>
                <li>
                  <a 
                    href="#" 
                    className="transition-colors text-sm hover:opacity-70" 
                    style={{ color: '#FAF7F0' }}
                    onClick={(e) => {
                      e.preventDefault();
                      openContactPopup();
                    }}
                  >
                    Contact
                  </a>
                </li>
              </ul>
            </div>
          </div>
          
          {/* Follow - centered on mobile, right side on desktop */}
          <div className="flex flex-col items-center md:items-end">
              <h3 className="mb-4" style={{ fontSize: '16px', fontWeight: 600, color: '#FAF7F0' }}>Follow</h3>
            <div className="flex gap-4">
              <button
                onClick={() => openPopup('Twitter', 'https://twitter.com/comparoo')}
                className="transition-colors"
                style={{ color: '#FAF7F0' }}
              >
                <Twitter className="h-5 w-5" />
              </button>
              <button
                onClick={() => openPopup('Instagram', 'https://instagram.com/comparoo')}
                className="transition-colors"
                style={{ color: '#FAF7F0' }}
              >
                <Instagram className="h-5 w-5" />
              </button>
              <button
                onClick={() => openPopup('YouTube', 'https://youtube.com/@comparoo')}
                className="transition-colors"
                style={{ color: '#FAF7F0' }}
              >
                <Youtube className="h-5 w-5" />
              </button>
            </div>
          </div>
        </div>
        
        {/* Bottom bar */}
                    <div className="pt-8 border-t" style={{ borderColor: 'rgba(255, 255, 255, 0.2)' }}>
                    <p className="text-sm text-center" style={{ color: '#FAF7F0' }}>
            © 2025 Comparoo | <Link 
              href="/terms"
              className="hover:text-white transition-colors" 
            >
              Terms of Service
            </Link> | All product names, logos, and brands are property of their respective owners.
          </p>
        </div>
      </div>

      {/* Link Popup */}
      <LinkPopup
        isOpen={popupState.isOpen}
        onClose={closePopup}
        title={popupState.title}
        link={popupState.link}
      />
    </footer>
  );
}