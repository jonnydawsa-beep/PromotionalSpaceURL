(function () {
  const $ = (id) => document.getElementById(id);
  const dealsRoot = $('deals');
  const emptyState = $('empty-state');
  const status = $('feed-status');
  const controls = $('deal-controls');
  const search = $('deal-search');
  const categoryFilter = $('category-filter');
  const sortFilter = $('sort-filter');
  const dealCount = $('deal-count');
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
    if (Number.isNaN(d.getTime())) return 'Check time unavailable';
    const mins = Math.max(0, Math.floor((Date.now() - d.getTime()) / 60000));
    if (mins < 2) return 'Checked just now';
    if (mins < 60) return `Checked ${mins} minutes ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `Checked ${hours} ${hours === 1 ? 'hour' : 'hours'} ago`;
    return `Checked ${d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}`;
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
      const image = d.image_url
        ? `<div class="deal-image"><img src="${escapeHtml(d.image_url)}" alt="" loading="lazy" referrerpolicy="no-referrer"></div>`
        : '<div class="deal-image placeholder" aria-hidden="true">↓</div>';
      const baselineNumber = Number(d.comparison_price);
      const currentNumber = Number(d.current_price);
      const baseline = Number.isFinite(baselineNumber)
        ? `<span class="was-price">Previously tracked ${money(baselineNumber)}</span>`
        : '';
      const saving = Number.isFinite(Number(d.saving_percent)) && Number(d.saving_percent) > 0
        ? `<span class="saving-badge"><svg class="saving-arrow" viewBox="0 0 16 16" aria-hidden="true" focusable="false"><path d="M8 2v9M4.5 8.5 8 12l3.5-3.5"/></svg>${pct(d.saving_percent)}</span>`
        : '';
      const savingCash = Number.isFinite(baselineNumber) && Number.isFinite(currentNumber) && baselineNumber > currentNumber
        ? `<p class="deal-saving-copy">${money(baselineNumber - currentNumber)} lower than our tracked price</p>`
        : '';
      const href = escapeHtml(d.affiliate_url || d.product_url || '#');
      const basis = d.price_basis === 'DELIVERED' ? 'Delivered price' : 'Item price';

      return `<article class="deal-card">
        ${image}
        <div class="deal-body">
          <div class="deal-topline"><span class="ad-label">Affiliate link</span>${saving}</div>
          <h3>${title}</h3>
          <p class="retailer-name">${retailer}</p>
          <div class="price-row"><strong>${money(d.current_price)}</strong>${baseline}</div>
          ${savingCash}
          <p class="deal-meta">${escapeHtml(basis)} · ${escapeHtml(checkedText(d.checked_at))}</p>
          <a class="deal-button" href="${href}" target="_blank" rel="sponsored nofollow noopener">See deal at ${retailer}</a>
          <p class="deal-small">Check the retailer for current stock, delivery and final price.</p>
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
      allDeals = Array.isArray(payload.deals) ? payload.deals.filter((d) => d && d.publishable !== false) : [];
      const count = allDeals.length;
      if (dealCount) dealCount.textContent = String(count);
      status.textContent = count ? `${count} live` : 'No live deals';
      status.classList.toggle('ok', count > 0);
      controls.hidden = count <= 1;
      populateCategories();
      render();
    })
    .catch(() => {
      if (dealCount) dealCount.textContent = '—';
      status.textContent = 'Feed unavailable';
      status.classList.add('warning');
      emptyState.hidden = false;
      emptyState.querySelector('h3').textContent = 'Deal feed temporarily unavailable';
      emptyState.querySelector('p').textContent = 'Please check again shortly.';
    });

  [search, categoryFilter, sortFilter].forEach((el) => el && el.addEventListener('input', render));
})();
