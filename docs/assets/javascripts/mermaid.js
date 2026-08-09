document$.subscribe(() => {
  if (typeof mermaid === "undefined") return;
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: "strict",
    theme: document.body.getAttribute("data-md-color-scheme") === "slate" ? "dark" : "neutral",
    fontFamily: "Inter, sans-serif",
  });
  mermaid.run({ querySelector: ".mermaid" });
});
