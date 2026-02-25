"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { NavSection } from "@/utils/docs";

interface SidebarProps {
  navigation: NavSection[];
  isOpen?: boolean;
  onClose?: () => void;
}

export function Sidebar({ navigation, isOpen, onClose }: SidebarProps) {
  const pathname = usePathname();

  // Remove leading/trailing slashes for comparison
  // Note: usePathname() returns path without basePath, so no need to strip /docs
  const currentSlug = pathname.replace(/^\//, "").replace(/\/$/, "");

  return (
    <aside className={`docs-sidebar ${isOpen ? "docs-sidebar-open" : ""}`}>
      <div className="docs-sidebar-logo">
        <a href="https://everyrow.io" className="docs-sidebar-logo-text">everyrow</a>
        <Link href="/" className="docs-sidebar-logo-chip" onClick={onClose}>docs</Link>
      </div>

      {navigation.map((section) => (
        <div key={section.title} className="docs-sidebar-section">
          {section.href ? (
            <Link href={section.href} className="docs-sidebar-section-title" onClick={onClose}>
              {section.title}
            </Link>
          ) : (
            <div className="docs-sidebar-section-title">{section.title}</div>
          )}
          <ul className="docs-sidebar-nav">
            {section.items.map((item) => {
              const isActive = currentSlug === item.slug;
              const isExternal = item.href?.startsWith("http");
              return (
                <li key={item.slug}>
                  {isExternal ? (
                    <a href={item.href} target="_blank" rel="noopener noreferrer">
                      {item.title}
                    </a>
                  ) : (
                    <Link
                      href={item.href || `/${item.slug}`}
                      className={isActive ? "active" : ""}
                      onClick={onClose}
                    >
                      {item.title}
                    </Link>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </aside>
  );
}
