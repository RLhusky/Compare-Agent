"use client";

import { Twitter, Instagram, Youtube } from 'lucide-react';
import { useState } from 'react';
import Link from 'next/link';
import { LinkPopup } from './LinkPopup';
import styles from './Footer.module.css';

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
    <footer className={styles.footer}>
      <div className={styles.container}>
        <div className={styles.grid}>
          {/* Company - centered on mobile, middle on desktop */}
          <div className={styles.companySection}>
            <div>
              <h3 className={styles.sectionTitle}>Company</h3>
              <ul className={styles.linkList}>
                <li className={styles.linkItem}>
                  <Link href="/about" className={styles.link}>
                    About
                  </Link>
                </li>
                <li className={styles.linkItem}>
                  <Link href="/how-it-works" className={styles.link}>
                    How It Works
                  </Link>
                </li>
                <li className={styles.linkItem}>
                  <button
                    onClick={openContactPopup}
                    className={styles.link}
                    style={{ background: 'none', border: 'none', cursor: 'pointer' }}
                    type="button"
                  >
                    Contact
                  </button>
                </li>
              </ul>
            </div>
          </div>

          {/* Follow - centered on mobile, right side on desktop */}
          <div className={styles.followSection}>
            <h3 className={styles.sectionTitle}>Follow</h3>
            <div className={styles.socialLinks}>
              <button
                onClick={() => openPopup('Twitter', 'https://twitter.com/comparoo')}
                className={styles.socialButton}
                type="button"
                aria-label="Follow us on Twitter"
              >
                <Twitter className={styles.socialIcon} />
              </button>
              <button
                onClick={() => openPopup('Instagram', 'https://instagram.com/comparoo')}
                className={styles.socialButton}
                type="button"
                aria-label="Follow us on Instagram"
              >
                <Instagram className={styles.socialIcon} />
              </button>
              <button
                onClick={() => openPopup('YouTube', 'https://youtube.com/@comparoo')}
                className={styles.socialButton}
                type="button"
                aria-label="Subscribe to our YouTube channel"
              >
                <Youtube className={styles.socialIcon} />
              </button>
            </div>
          </div>
        </div>

        {/* Bottom bar */}
        <div className={styles.bottomBar}>
          <p className={styles.copyright}>
            © 2025 Comparoo |{' '}
            <Link href="/terms">
              Terms of Service
            </Link>{' '}
            | All product names, logos, and brands are property of their respective owners.
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
