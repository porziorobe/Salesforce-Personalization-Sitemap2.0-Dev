(function () {
  var pageUrlInput = document.getElementById('page-url');
  var customerNameInput = document.getElementById('customer-name');
  var detectBtn = document.getElementById('detect-btn');
  var detectedFields = document.getElementById('detected-fields');
  var targetSelectorInput = document.getElementById('target-selector');
  var targetHtmlInput = document.getElementById('target-html');
  var manualToggle = document.getElementById('manual-toggle');
  var recSelectorInput = document.getElementById('rec-selector');

  var generateSitemapBtn = document.getElementById('generate-sitemap-btn');
  var generateHeroBtn = document.getElementById('generate-hero-btn');
  var generateRecBtn = document.getElementById('generate-rec-btn');

  var outputArea = document.getElementById('output');
  var heroTemplateOutput = document.getElementById('hero-template-output');
  var recTemplateOutput = document.getElementById('rec-template-output');

  var copyBtn = document.getElementById('copy-btn');
  var copyHeroBtn = document.getElementById('copy-hero-btn');
  var copyRecBtn = document.getElementById('copy-rec-btn');

  var heroFeedbackBtn = document.getElementById('hero-feedback-btn');
  var feedbackModal = document.getElementById('feedback-modal');
  var feedbackNote = document.getElementById('feedback-note');
  var regenerateBtn = document.getElementById('regenerate-btn');
  var issueCheckboxes = document.querySelectorAll('input[name="fb-issue"]');

  var errorBanner = document.getElementById('error-banner');
  var extractingIndicator = document.getElementById('extracting-indicator');

  var historyList = document.getElementById('history-list');
  var clearHistoryBtn = document.getElementById('clear-history-btn');
  var HISTORY_KEY = 'sitemap_history';
  var HISTORY_MAX = 50;

  var extractedStyles = null;
  var stylesReady = false;

  var TIMEOUT_MSG = 'The AI service timed out — try again, or pick a simpler parent element if the problem persists.';

  function setBtnLoading(btn, loading) {
    btn.disabled = loading;
    btn.classList.toggle('is-loading', loading);
    var loadingEl = btn.querySelector('.btn-loading');
    if (loadingEl) loadingEl.hidden = !loading;
  }

  function showError(message) {
    errorBanner.textContent = message;
    errorBanner.hidden = false;
  }

  function clearError() {
    errorBanner.textContent = '';
    errorBanner.hidden = true;
  }

  function setEditable(editable) {
    targetSelectorInput.readOnly = !editable;
    targetHtmlInput.readOnly = !editable;
  }

  function heroInputsReady() {
    return targetSelectorInput.value.trim() && targetHtmlInput.value.trim();
  }

  function refreshSectionButtons() {
    var ready = heroInputsReady();
    generateSitemapBtn.disabled = !ready;
    generateHeroBtn.disabled = !ready;
  }

  async function extractStyles(pageUrl, targetSelector) {
    extractingIndicator.hidden = false;
    stylesReady = false;
    try {
      var response = await fetch('/extract-styles', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pageUrl: pageUrl, targetSelector: targetSelector }),
      });
      var data = await response.json().catch(function () { return {}; });
      if (!response.ok) throw new Error(data.error || 'Style extraction failed.');
      extractedStyles = data.extractedStyles || null;
      stylesReady = true;
    } finally {
      extractingIndicator.hidden = true;
    }
  }

  async function detectHero() {
    clearError();
    var pageUrl = pageUrlInput.value.trim();
    if (!pageUrl) {
      showError('Please enter a Customer Website URL.');
      return;
    }

    setBtnLoading(detectBtn, true);
    try {
      var response = await fetch('/detect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pageUrl: pageUrl }),
      });
      var data = await response.json().catch(function () { return {}; });
      if (!response.ok) {
        showError('Could not access this site automatically. Enter the CSS selector and element HTML below.');
        detectedFields.hidden = false;
        manualToggle.checked = true;
        setEditable(true);
        refreshSectionButtons();
        return;
      }

      targetSelectorInput.value = data.selector || '';
      targetHtmlInput.value = data.outerHtml || '';
      detectedFields.hidden = false;
      manualToggle.checked = false;
      setEditable(false);

      try {
        await extractStyles(pageUrl, targetSelectorInput.value.trim());
      } catch (extractErr) {
        showError(extractErr.message || 'Style extraction failed.');
      }
      refreshSectionButtons();
    } catch (err) {
      showError('Could not access this site automatically. Enter the CSS selector and element HTML below.');
      detectedFields.hidden = false;
      manualToggle.checked = true;
      setEditable(true);
      refreshSectionButtons();
    } finally {
      setBtnLoading(detectBtn, false);
    }
  }

  async function generateSitemap() {
    clearError();
    if (!heroInputsReady()) {
      showError('Detect or fill in the hero element first.');
      return;
    }
    setBtnLoading(generateSitemapBtn, true);
    try {
      var response = await fetch('/assemble-sitemap', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          heroSelector: targetSelectorInput.value.trim(),
          recSelector: recSelectorInput.value.trim(),
        }),
      });
      var data = await response.json().catch(function () { return {}; });
      if (!response.ok) {
        showError(data.error || 'Sitemap assembly failed.');
        return;
      }
      outputArea.value = data.sitemap || '';
      copyBtn.disabled = !outputArea.value;
      addHistoryEntry(pageUrlInput.value.trim(), { sitemap: data.sitemap });
    } catch (err) {
      showError('Network error during sitemap assembly. Try again.');
    } finally {
      setBtnLoading(generateSitemapBtn, false);
    }
  }

  async function generateHero() {
    clearError();
    var pageUrl = pageUrlInput.value.trim();
    var targetSelector = targetSelectorInput.value.trim();
    var targetHtml = targetHtmlInput.value;
    if (!pageUrl || !targetSelector || !targetHtml.trim()) {
      showError('Detect or fill in the hero element first.');
      return;
    }

    setBtnLoading(generateHeroBtn, true);
    try {
      var response = await fetch('/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pageUrl: pageUrl,
          targetSelector: targetSelector,
          targetHtml: targetHtml,
          extractedStyles: extractedStyles,
          customerName: customerNameInput.value.trim(),
        }),
      });
      var data = await response.json().catch(function () { return {}; });
      if (!response.ok) {
        if (response.status >= 502 && response.status <= 504) showError(TIMEOUT_MSG);
        else showError(data.error || 'Hero generation failed (' + response.status + ').');
        return;
      }
      if (!data.heroTemplate) {
        showError('Hero generation returned empty output.');
        return;
      }
      heroTemplateOutput.value = data.heroTemplate;
      copyHeroBtn.disabled = false;
      heroFeedbackBtn.disabled = false;
      addHistoryEntry(pageUrl, { heroTemplate: data.heroTemplate });
    } catch (err) {
      showError(err.name === 'TypeError' ? TIMEOUT_MSG : 'Network error during hero generation. Try again.');
    } finally {
      setBtnLoading(generateHeroBtn, false);
    }
  }

  async function generateRecommendations() {
    clearError();
    setBtnLoading(generateRecBtn, true);
    try {
      var response = await fetch('/recommendations-template', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      var data = await response.json().catch(function () { return {}; });
      if (!response.ok) {
        showError(data.error || 'Recommendations template failed.');
        return;
      }
      recTemplateOutput.value = data.recTemplate || '';
      copyRecBtn.disabled = !recTemplateOutput.value;
    } catch (err) {
      showError('Network error during recommendations generation. Try again.');
    } finally {
      setBtnLoading(generateRecBtn, false);
    }
  }

  async function regenerateHeroWithFeedback() {
    clearError();
    var issues = getCheckedIssues();
    var note = feedbackNote.value.trim();
    if (issues.length === 0 && !note) {
      showError('Select an issue or provide feedback text.');
      return;
    }

    setBtnLoading(regenerateBtn, true);
    try {
      var response = await fetch('/regenerate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pageUrl: pageUrlInput.value.trim(),
          targetSelector: targetSelectorInput.value.trim(),
          targetHtml: targetHtmlInput.value,
          extractedStyles: extractedStyles,
          previousOutput: heroTemplateOutput.value,
          issues: issues,
          feedbackNote: note,
          customerName: customerNameInput.value.trim(),
        }),
      });
      var data = await response.json().catch(function () { return {}; });
      if (!response.ok) {
        if (response.status >= 502 && response.status <= 504) showError(TIMEOUT_MSG);
        else showError(data.error || 'Regeneration failed (' + response.status + ').');
        return;
      }
      if (!data.heroTemplate) {
        showError('Regeneration returned empty output.');
        return;
      }
      heroTemplateOutput.value = data.heroTemplate;
      copyHeroBtn.disabled = false;
      addHistoryEntry(pageUrlInput.value.trim(), { heroTemplate: data.heroTemplate });
      closeFeedbackModal();
    } catch (err) {
      showError(err.name === 'TypeError' ? TIMEOUT_MSG : 'Network error during regeneration. Try again.');
    } finally {
      setBtnLoading(regenerateBtn, false);
    }
  }

  function getCheckedIssues() {
    var issues = [];
    issueCheckboxes.forEach(function (cb) { if (cb.checked) issues.push(cb.value); });
    return issues;
  }

  function updateRegenerateEnabled() {
    regenerateBtn.disabled = getCheckedIssues().length === 0 && !feedbackNote.value.trim();
  }

  function openFeedbackModal() {
    if (!heroTemplateOutput.value) return;
    feedbackModal.hidden = false;
    document.body.classList.add('modal-open');
    updateRegenerateEnabled();
  }

  function closeFeedbackModal() {
    feedbackModal.hidden = true;
    document.body.classList.remove('modal-open');
    feedbackNote.value = '';
    issueCheckboxes.forEach(function (cb) { cb.checked = false; });
    regenerateBtn.disabled = true;
  }

  pageUrlInput.addEventListener('blur', function () {
    if (pageUrlInput.value.trim() && !customerNameInput.value.trim()) {
      customerNameInput.value = deriveBrand(pageUrlInput.value.trim());
    }
  });

  detectBtn.addEventListener('click', detectHero);
  generateSitemapBtn.addEventListener('click', generateSitemap);
  generateHeroBtn.addEventListener('click', generateHero);
  generateRecBtn.addEventListener('click', generateRecommendations);
  heroFeedbackBtn.addEventListener('click', openFeedbackModal);
  regenerateBtn.addEventListener('click', regenerateHeroWithFeedback);

  feedbackModal.addEventListener('click', function (e) {
    if (e.target.hasAttribute('data-close-modal')) closeFeedbackModal();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !feedbackModal.hidden) closeFeedbackModal();
  });

  issueCheckboxes.forEach(function (cb) { cb.addEventListener('change', updateRegenerateEnabled); });
  feedbackNote.addEventListener('input', updateRegenerateEnabled);

  manualToggle.addEventListener('change', function () { setEditable(this.checked); });
  targetSelectorInput.addEventListener('input', refreshSectionButtons);
  targetHtmlInput.addEventListener('input', refreshSectionButtons);

  function wireCopyButton(btn, source) {
    btn.addEventListener('click', async function () {
      if (!source.value) return;
      try {
        await navigator.clipboard.writeText(source.value);
        var original = btn.textContent;
        btn.textContent = 'Copied!';
        btn.disabled = true;
        setTimeout(function () {
          btn.textContent = original;
          btn.disabled = !source.value;
        }, 1500);
      } catch (e) {
        showError('Could not copy to clipboard.');
      }
    });
  }
  wireCopyButton(copyBtn, outputArea);
  wireCopyButton(copyHeroBtn, heroTemplateOutput);
  wireCopyButton(copyRecBtn, recTemplateOutput);

  function deriveBrand(url) {
    try {
      var host = new URL(url).hostname.replace(/^www\./, '');
      var name = host.split('.')[0];
      return name.charAt(0).toUpperCase() + name.slice(1);
    } catch (_) {
      return 'Unknown';
    }
  }

  function getHistory() {
    try { return JSON.parse(localStorage.getItem(HISTORY_KEY)) || []; }
    catch (_) { return []; }
  }

  function saveHistory(entries) {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(entries.slice(0, HISTORY_MAX)));
  }

  function addHistoryEntry(url, partial) {
    var entries = getHistory();
    entries.unshift({
      id: String(Date.now()),
      brand: deriveBrand(url),
      url: url,
      timestamp: Date.now(),
      sitemap: partial.sitemap || '',
      heroTemplate: partial.heroTemplate || '',
      recTemplate: partial.recTemplate || '',
    });
    saveHistory(entries);
    renderHistory();
  }

  function deleteHistoryEntry(id) {
    saveHistory(getHistory().filter(function (e) { return e.id !== id; }));
    renderHistory();
  }

  function timeAgo(ts) {
    var diff = Math.floor((Date.now() - ts) / 1000);
    if (diff < 60) return 'Just now';
    if (diff < 3600) return Math.floor(diff / 60) + ' min ago';
    if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
    if (diff < 172800) return 'Yesterday';
    return new Date(ts).toLocaleDateString();
  }

  function renderHistory() {
    var entries = getHistory();
    clearHistoryBtn.hidden = entries.length === 0;

    if (entries.length === 0) {
      historyList.innerHTML = '<p class="history-empty">No artifacts generated yet.</p>';
      return;
    }

    historyList.innerHTML = entries.map(function (entry) {
      return '<div class="history-card" data-id="' + entry.id + '">'
        + '<div class="history-card-info">'
        + '<span class="history-brand">' + entry.brand + '</span>'
        + '<span class="history-url" title="' + entry.url + '">' + entry.url + '</span>'
        + '</div>'
        + '<span class="history-time">' + timeAgo(entry.timestamp) + '</span>'
        + '<div class="history-actions">'
        + '<button type="button" class="history-btn history-btn--load">Load</button>'
        + '<button type="button" class="history-btn history-btn--delete">Delete</button>'
        + '</div>'
        + '</div>';
    }).join('');
  }

  historyList.addEventListener('click', function (e) {
    var btn = e.target.closest('.history-btn');
    if (!btn) return;
    var card = btn.closest('.history-card');
    var id = card.dataset.id;
    var entries = getHistory();
    var entry = entries.find(function (e) { return e.id === id; });
    if (!entry) return;

    if (btn.classList.contains('history-btn--load')) {
      if (entry.sitemap) { outputArea.value = entry.sitemap; copyBtn.disabled = false; }
      if (entry.heroTemplate) {
        heroTemplateOutput.value = entry.heroTemplate;
        copyHeroBtn.disabled = false;
        heroFeedbackBtn.disabled = false;
      }
      if (entry.recTemplate) { recTemplateOutput.value = entry.recTemplate; copyRecBtn.disabled = false; }
      outputArea.scrollIntoView({ behavior: 'smooth', block: 'center' });
    } else if (btn.classList.contains('history-btn--delete')) {
      deleteHistoryEntry(id);
    }
  });

  clearHistoryBtn.addEventListener('click', function () {
    if (!confirm('Clear all generation history?')) return;
    localStorage.removeItem(HISTORY_KEY);
    renderHistory();
  });

  renderHistory();
})();
