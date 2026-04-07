/* ============================================================
   Cody – Main Script
   ============================================================ */

'use strict';

/* ---------- Nav: scrolled glass effect ---------- */
function initNav() {
  const navbar = document.querySelector('.navbar');
  if (!navbar) return;

  const onScroll = () => {
    navbar.classList.toggle('scrolled', window.scrollY > 10);
  };
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();
}

/* ---------- Hamburger menu ---------- */
function initHamburger() {
  const btn   = document.querySelector('.hamburger');
  const links = document.querySelector('.nav-links');
  if (!btn || !links) return;

  const closeMenu = () => {
    btn.classList.remove('open');
    btn.setAttribute('aria-expanded', 'false');
    links.classList.remove('open');
  };

  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const isOpen = btn.classList.toggle('open');
    btn.setAttribute('aria-expanded', String(isOpen));
    links.classList.toggle('open', isOpen);
  });

  document.addEventListener('click', (e) => {
    if (!btn.contains(e.target) && !links.contains(e.target)) {
      closeMenu();
    }
  });

  // Close on nav link click
  links.querySelectorAll('a').forEach(a => a.addEventListener('click', closeMenu));
}

/* ---------- Scroll Animations (IntersectionObserver) ---------- */
function initScrollAnimations() {
  const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (prefersReduced) {
    document.querySelectorAll('.anim').forEach(el => el.classList.add('visible'));
    return;
  }

  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });

  document.querySelectorAll('.anim').forEach(el => observer.observe(el));
}

/* ---------- Copy Buttons ---------- */
function initCopyButtons() {
  document.querySelectorAll('.copy-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const block = btn.closest('.code-block');
      if (!block) return;

      const pre = block.querySelector('pre');
      if (!pre) return;

      // Strip only leading "$ " prompts from line starts, preserve content
      const raw = pre.innerText || pre.textContent || '';
      const cleaned = raw.replace(/^[$#]\s/gm, '').trim();

      const doCopy = (text) => {
        if (navigator.clipboard && window.isSecureContext) {
          return navigator.clipboard.writeText(text);
        }
        // Fallback for file:// or HTTP
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.cssText = 'position:fixed;top:-9999px;left:-9999px;opacity:0';
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand('copy'); } catch (_) {}
        document.body.removeChild(ta);
        return Promise.resolve();
      };

      doCopy(cleaned).then(() => {
        const prev = btn.textContent;
        btn.textContent = 'Copied!';
        btn.classList.add('copied');
        setTimeout(() => {
          btn.textContent = prev;
          btn.classList.remove('copied');
        }, 2000);
      }).catch(() => {
        btn.textContent = 'Failed';
        setTimeout(() => { btn.textContent = 'Copy'; }, 2000);
      });
    });
  });
}

/* ---------- Docs Sidebar Scroll Highlight ---------- */
function initDocsSidebar() {
  const sidebar = document.querySelector('.docs-sidebar');
  if (!sidebar) return;

  const navLinks = Array.from(sidebar.querySelectorAll('.sidebar-nav a[href^="#"]'));
  if (!navLinks.length) return;

  const headings = navLinks.map(a => document.querySelector(a.getAttribute('href'))).filter(Boolean);

  const setActive = (link) => {
    navLinks.forEach(a => a.classList.remove('active'));
    if (link) link.classList.add('active');
  };

  // Ensure at least the first link stays active if nothing else matches
  setActive(navLinks[0]);

  const observer = new IntersectionObserver((entries) => {
    // Find the topmost visible heading
    const visible = headings.filter(h => {
      const rect = h.getBoundingClientRect();
      return rect.top <= 120 && rect.bottom > 0;
    });

    if (visible.length === 0) {
      // Pick the last heading above the fold
      const above = headings.filter(h => h.getBoundingClientRect().top < 120);
      if (above.length > 0) {
        const last = above[above.length - 1];
        const idx = headings.indexOf(last);
        setActive(navLinks[idx]);
      }
      return;
    }

    const first = visible[0];
    const idx = headings.indexOf(first);
    if (idx !== -1) setActive(navLinks[idx]);
  }, { rootMargin: '-60px 0px -60% 0px', threshold: 0 });

  headings.forEach(h => observer.observe(h));
}

/* ---------- Tab Panels (install section) ---------- */
function initTabs() {
  document.querySelectorAll('.install-tabs').forEach(tabGroup => {
    const buttons = tabGroup.querySelectorAll('.tab-btn');
    const container = tabGroup.closest('.install-block') || tabGroup.parentElement;

    buttons.forEach(btn => {
      btn.addEventListener('click', () => {
        const target = btn.dataset.tab;
        buttons.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');

        container.querySelectorAll('.tab-panel').forEach(panel => {
          panel.classList.toggle('active', panel.dataset.panel === target);
        });
      });
    });
  });
}

/* ---------- Number Counter Animation ---------- */
function initCounters() {
  const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const counters = document.querySelectorAll('[data-count]');
  if (!counters.length) return;

  const animateCounter = (el) => {
    const target = parseFloat(el.dataset.count);
    const suffix = el.dataset.suffix || '';
    const duration = target <= 1000 ? 900 : 1400;
    const start = performance.now();

    const tick = (now) => {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = Math.round(eased * target);
      el.textContent = current + suffix;
      if (progress < 1) requestAnimationFrame(tick);
    };

    requestAnimationFrame(tick);
  };

  if (prefersReduced) {
    counters.forEach(el => {
      el.textContent = el.dataset.count + (el.dataset.suffix || '');
    });
    return;
  }

  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        animateCounter(entry.target);
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.5 });

  counters.forEach(el => observer.observe(el));
}

/* ---------- Terminal Animation ---------- */
function initTerminal() {
  const terminal = document.querySelector('.terminal-body');
  if (!terminal) return;

  const lines = [
    { text: '$ pip install cody-ai', type: 'cmd', delay: 0 },
    { text: 'Collecting cody-ai...', type: 'output', delay: 600 },
    { text: 'Successfully installed cody-ai-2.0.2', type: 'output', delay: 1000 },
    { text: '', type: 'blank', delay: 1200 },
    { text: '$ python', type: 'cmd', delay: 1400 },
    { text: '>>> from cody import AsyncCodyClient', type: 'output', delay: 1900 },
    { text: '>>> import asyncio', type: 'output', delay: 2100 },
    { text: '', type: 'blank', delay: 2200 },
    { text: '>>> async def main():', type: 'output', delay: 2400 },
    { text: '...     async with AsyncCodyClient(', type: 'output', delay: 2500 },
    { text: '...         workdir="/my/project"', type: 'output', delay: 2600 },
    { text: '...     ) as client:', type: 'output', delay: 2700 },
    { text: '...         result = await client.run(', type: 'output', delay: 2800 },
    { text: '...             "Add type hints to utils.py"', type: 'output', delay: 2900 },
    { text: '...         )', type: 'output', delay: 3000 },
    { text: '...         print(result.output)', type: 'output', delay: 3100 },
    { text: '', type: 'blank', delay: 3300 },
    { text: '>>> asyncio.run(main())', type: 'output', delay: 3500 },
    { text: '', type: 'blank', delay: 3700 },
    { text: '✓ Reading utils.py...', type: 'green', delay: 3900 },
    { text: '✓ Analyzing function signatures...', type: 'green', delay: 4300 },
    { text: '✓ Adding type hints to 12 functions...', type: 'green', delay: 4800 },
    { text: '✓ Writing updated file...', type: 'green', delay: 5300 },
    { text: '', type: 'blank', delay: 5500 },
    { text: 'Added type hints to utils.py (12 functions).', type: 'blue', delay: 5700 },
    { text: 'session_id: ses_a1b2c3d4', type: 'dim', delay: 5900 },
  ];

  const colorMap = {
    cmd:    'color: #f0f6fc',
    output: 'color: #8b949e',
    green:  'color: #4ade80',
    blue:   'color: #52c4f7',
    dim:    'color: #484f58',
    blank:  '',
  };

  let started = false;

  const runAnimation = () => {
    if (started) return;
    started = true;
    terminal.innerHTML = '';

    lines.forEach(({ text, type, delay }) => {
      setTimeout(() => {
        const span = document.createElement('span');
        const style = colorMap[type] || '';

        if (type === 'cmd') {
          span.innerHTML = `<span style="color:#4ade80">$ </span><span style="color:#f0f6fc">${escHtml(text.slice(2))}</span>`;
        } else {
          span.innerHTML = text ? `<span style="${style}">${escHtml(text)}</span>` : ' ';
        }

        span.style.display = 'block';
        terminal.appendChild(span);
        terminal.scrollTop = terminal.scrollHeight;
      }, delay);
    });
  };

  const observer = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting) {
      runAnimation();
      observer.unobserve(terminal);
    }
  }, { threshold: 0.3 });

  observer.observe(terminal);
}

function escHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

/* ---------- Active Nav Link (docs page) ---------- */
function initActiveNavLink() {
  const path = window.location.pathname;
  document.querySelectorAll('.nav-links a').forEach(a => {
    const href = a.getAttribute('href') || '';
    if (
      (path.endsWith('docs.html') && href.includes('docs')) ||
      (path.endsWith('index.html') && href.includes('index')) ||
      (path === '/' && href.includes('index'))
    ) {
      a.classList.add('active');
    }
  });
}

/* ---------- Bootstrap ---------- */
document.addEventListener('DOMContentLoaded', () => {
  initNav();
  initHamburger();
  initScrollAnimations();
  initCopyButtons();
  initDocsSidebar();
  initTabs();
  initCounters();
  initTerminal();
  initActiveNavLink();
});
