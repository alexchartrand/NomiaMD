import { useEffect } from "react";
import { useLocation } from "react-router-dom";

// BrowserRouter keeps the scroll position across navigations and ignores `#anchors` on a
// route change — so a link to `/#faq` from another page would land at the top (or worse,
// mid-page). Scroll to the anchor when there is one, to the top otherwise.
//
// Keyed on `location.key`, not the URL: clicking a link to the URL already shown (the same
// `/#fonctionnement` twice, after scrolling away) is still a new navigation with a new key,
// and should scroll again.
export function ScrollToTop() {
  const { hash, key } = useLocation();

  useEffect(() => {
    if (hash) {
      // Next frame: the target section is rendered by then on a fresh page.
      const frame = requestAnimationFrame(() => {
        document.getElementById(decodeURIComponent(hash.slice(1)))?.scrollIntoView({ behavior: "smooth" });
      });
      return () => cancelAnimationFrame(frame);
    }
    window.scrollTo(0, 0);
  }, [hash, key]);

  return null;
}
