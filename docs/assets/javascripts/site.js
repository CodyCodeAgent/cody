document$.subscribe(() => {
  const cards = document.querySelectorAll(".reveal-card");
  if (!cards.length || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      });
    },
    { threshold: 0.12 }
  );
  cards.forEach((card) => observer.observe(card));
});
