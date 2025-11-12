"use client";

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { LinkPopup } from './LinkPopup';
import styles from './Header.module.css';

export function Header() {
  const pathname = usePathname();
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

  // Helper to check if nav link is active
  const isActiveLink = (path: string) => {
    if (path === '/' && pathname === '/') return true;
    if (path !== '/' && pathname?.startsWith(path)) return true;
    return false;
  };

  return (
    <header className={styles.header}>
      <div className={styles.container}>
        {/* Kangaroo logo on the left */}
        <Link href="/" className={styles.logo} aria-label="Comparoo Home">
          <img
            src="/885c32b6b5c1d7631a690c5de5c363d2e8cc3f37.png"
            alt="Comparoo Logo"
            className={styles.logoImage}
          />
        </Link>

        {/* Navigation in the middle */}
        <nav className={styles.nav} aria-label="Main navigation">
          <Link
            href="/"
            className={`${styles.navLink} ${isActiveLink('/') ? styles.active : ''}`}
          >
            Home
          </Link>
          <Link
            href="/how-it-works"
            className={`${styles.navLink} ${isActiveLink('/how-it-works') ? styles.active : ''}`}
          >
            How It Works
          </Link>
          <Link
            href="/about"
            className={`${styles.navLink} ${isActiveLink('/about') ? styles.active : ''}`}
          >
            About
          </Link>
        </nav>

        {/* Contact Us on the right */}
        <div className={styles.actions}>
          <button
            onClick={openContactPopup}
            className={styles.contactButton}
            type="button"
            aria-label="Contact Us"
          >
            Contact Us
          </button>
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
