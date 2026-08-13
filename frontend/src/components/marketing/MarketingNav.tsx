"use client";

import { ArrowRight, ExternalLink, ShieldHalf } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import styles from "./MarketingNav.module.css";

const SECTION_LINKS = [
  { href: "#platform", label: "Platform" },
  { href: "#intelligence", label: "Intelligence" },
  { href: "#workflow", label: "Workflow" },
  { href: "#architecture", label: "Architecture" },
];

export function MarketingNav() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    function onScroll() {
      setScrolled(window.scrollY > 8);
    }
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <nav className={cn(styles.nav, scrolled && styles.navScrolled)}>
      <Link href="/" className={styles.brand}>
        <span className={styles.brandMark}>
          <ShieldHalf size={16} strokeWidth={2} />
        </span>
        ARGUS
      </Link>

      <div className={styles.links}>
        {SECTION_LINKS.map((item) => (
          <a key={item.href} href={item.href} className={styles.link}>
            {item.label}
          </a>
        ))}
      </div>

      <div className={styles.actions}>
        <a
          href="https://github.com/Ayush-o1/Argus"
          target="_blank"
          rel="noreferrer"
          className={styles.ghostLink}
        >
          <ExternalLink size={14} />
          <span>Source</span>
        </a>
        <Link href="/dashboard">
          <Button variant="primary" size="sm">
            Enter Argus <ArrowRight size={14} />
          </Button>
        </Link>
      </div>
    </nav>
  );
}
