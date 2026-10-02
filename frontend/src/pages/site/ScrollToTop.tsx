import { useEffect } from "react";
import { useLocation } from "react-router-dom";

// BrowserRouter keeps the scroll position across navigations and ignores `#anchors` on a
// route change — so a link to `/#faq` from another page would land at the top (or worse,
// mid-page). Scroll to the anchor when there is one, to the top otherwise.
export function ScrollToTop() {
  const { pathname, hash } = useLocation();

  useEffect(() => {
    if (hash) {
      // Next frame: the target section is rendered by then on a fresh page.
      const frame = requestAnimationFrame(() => {
        document.getElementById(decodeURIComponent(hash.slice(1)))?.scrollIntoView({ behavior: "smooth" });
      });
      return () => cancelAnimationFrame(frame);
    }
    window.scrollTo(0, 0);
  }, [pathname, hash]);

  return null;
}
