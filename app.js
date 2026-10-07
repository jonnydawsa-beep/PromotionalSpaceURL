(function () {
  const $ = (id) => document.getElementById(id);
  const dealsRoot = $('deals');
  const emptyState = $('empty-state');
  const status = $('feed-status');
  const controls = $('deal-controls');
  const search = $('deal-search');
  const categoryFilter = $('category-filter');
  const sortFilter = $('sort-filter');
  const year = $('year');
  if (year) year.textContent = new Date().getFullYear();

  const toggle = document.querySelector('.nav-toggle');
  const nav = document.getElementById('primary-nav');
  if (toggle && nav) {
    toggle.addEventListener('click', () => {
      const open = toggle.getAttribute('aria-expanded') === 'true';
      toggle.setAttribute('aria-expanded', String(!open));
      nav.classList.toggle('open', !open);
    });
  }

  if (!dealsRoot) return;

  let allDeals = [];
  let feedMeta = {};

  const money = (value) => {
    const n = Number(value);
    if (!Number.isFinite(n)) return '—';
    return new Intl.NumberFormat('en-GB', { style: 'currency', currency: 'GBP' }).format(n);
  };

  const pct = (value) => {
    const n = Number(value);
    return Number.isFinite(n) ? `${n.toFixed(n >= 10 ? 0 : 1)}%` : '—';
  };

  const checkedText = (value) => {
    if (!value) return 'Check time unavailable';
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return `Checked ${value}`;
    return `Checked ${d.toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })}`;
  };

  const escapeHtml = (value) => String(value ?? '').replace(/[&<>'"]/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  }[c]));

  function render() {
    const query = (search?.value || '').trim().toLowerCase();
    const category = categoryFilter?.value || 'all';
    const sort = sortFilter?.value || 'newest';

    let rows = allDeals.filter((d) => {
      const haystack = [d.title, d.brand, d.retailer, d.category].filter(Boolean).join(' ').toLowerCase();
      return (!query || haystack.includes(query)) && (category === 'all' || d.category === category);
    });

    rows.sort((a, b) => {
      if (sort === 'saving') return Number(b.saving_percent || 0) - Number(a.saving_percent || 0);
      if (sort === 'price-low') return Number(a.current_price || Infinity) - Number(b.current_price || Infinity);
      return new Date(b.checked_at || 0) - new Date(a.checked_at || 0);
    });

    if (!rows.length) {
      dealsRoot.innerHTML = '';
      emptyState.hidden = false;
      return;
    }
    emptyState.hidden = true;

    dealsRoot.innerHTML = rows.map((d) => {
      const title = escapeHtml(d.title || 'Product offer');
      const retailer = escapeHtml(d.retailer || 'Retailer');
      const image = d.image_url ? `<div class="deal-image"><img src="${escapeHtml(d.image_url)}" alt="" loading="lazy" referrerpolicy="no-referrer"></div>` : `<div class="deal-image placeholder" aria-hidden="true">£</div>`;
      const basis = d.price_basis === 'DELIVERED' ? 'Delivered-price comparison' : 'Item-price comparison';
      const baseline = Number.isFinite(Number(d.comparison_price)) ? `<span class="was-price">Compared with ${money(d.comparison_price)}</span>` : '';
      const saving = Number.isFinite(Number(d.saving_percent)) && Number(d.saving_percent) > 0 ? `<span class="saving-badge">Save ${pct(d.saving_percent)}</span>` : '';
      const href = escapeHtml(d.affiliate_url || d.product_url || '#');
      return `<article class="deal-card">
        ${image}
        <div class="deal-body">
          <div class="deal-topline"><span class="ad-label">Ad</span>${saving}</div>
          <h3>${title}</h3>
          <p class="retailer-name">${retailer}</p>
          <div class="price-row"><strong>${money(d.current_price)}</strong>${baseline}</div>
          <p class="deal-meta">${escapeHtml(basis)} · ${escapeHtml(checkedText(d.checked_at))}</p>
          <a class="button deal-button" href="${href}" target="_blank" rel="sponsored nofollow noopener">View at ${retailer}</a>
          <p class="deal-small">Price and stock may have changed. Confirm on the retailer site.</p>
        </div>
      </article>`;
    }).join('');
  }

  function populateCategories() {
    const cats = [...new Set(allDeals.map((d) => d.category).filter(Boolean))].sort();
    if (!categoryFilter) return;
    cats.forEach((cat) => {
      const option = document.createElement('option');
      option.value = cat;
      option.textContent = cat;
      categoryFilter.appendChild(option);
    });
  }

  fetch('deals.json', { cache: 'no-store' })
    .then((r) => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    })
    .then((payload) => {
      feedMeta = payload.meta || {};
      allDeals = Array.isArray(payload.deals) ? payload.deals.filter((d) => d && d.publishable !== false) : [];
      const count = allDeals.length;
      status.textContent = count ? `${count} verified ${count === 1 ? 'offer' : 'offers'} live` : 'No verified offers live';
      status.classList.toggle('ok', count > 0);
      controls.hidden = count === 0;
      populateCategories();
      render();
    })
    .catch(() => {
      status.textContent = 'Feed temporarily unavailable';
      status.classList.add('warning');
      emptyState.hidden = false;
      emptyState.querySelector('h3').textContent = 'Offer feed temporarily unavailable';
      emptyState.querySelector('p').textContent = 'The public comparison feed could not be loaded. Please check again later.';
    });

  [search, categoryFilter, sortFilter].forEach((el) => el && el.addEventListener('input', render));
})();
