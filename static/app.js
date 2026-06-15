(function () {
  var pageUrlInput = document.getElementById('page-url');
  var customerNameInput = document.getElementById('customer-name');
  var detectBtn = document.getElementById('detect-btn');
  var detectedFields = document.getElementById('detected-fields');
  var targetSelectorInput = document.getElementById('target-selector');
  var targetHtmlInput = document.getElementById('target-html');
  var recContainerSelectorInput = document.getElementById('rec-container-selector');
  var recContainerHtmlInput = document.getElementById('rec-container-html');
  var recHtmlInput = document.getElementById('rec-html');
  var recStatusNote = document.getElementById('rec-status-note');

  var generateSitemapBtn = document.getElementById('generate-sitemap-btn');
  var generateHeroBtn = document.getElementById('generate-hero-btn');
  var generateRecBtn = document.getElementById('generate-rec-btn');
  var defaultHeroBtn = document.getElementById('default-hero-btn');
  var defaultRecBtn = document.getElementById('default-rec-btn');

  var openSitemapBtn = document.getElementById('open-sitemap-btn');
  var openHeroBtn = document.getElementById('open-hero-btn');
  var openRecBtn = document.getElementById('open-rec-btn');

  var copyBtn = document.getElementById('copy-btn');
  var copyHeroBtn = document.getElementById('copy-hero-btn');
  var copyRecBtn = document.getElementById('copy-rec-btn');

  var modal = document.getElementById('artifact-modal');
  var modalHeading = document.getElementById('artifact-modal-heading');
  var modalTabs = document.getElementById('modal-tabs');
  var modalTabButtons = modal.querySelectorAll('.modal-tab');
  var modalCodePanel = document.getElementById('modal-tab-code');
  var modalRefinePanel = document.getElementById('modal-tab-refine');
  var modalCode = document.getElementById('modal-code');
  var modalCopyBtn = document.getElementById('modal-copy-btn');
  var feedbackNote = document.getElementById('feedback-note');
  var regenerateBtn = document.getElementById('regenerate-btn');
  var heroFeedbackChecks = document.getElementById('hero-feedback-checks');
  var recFeedbackChecks = document.getElementById('rec-feedback-checks');
  var heroIssueCheckboxes = document.querySelectorAll('input[name="fb-issue"]');
  var recIssueCheckboxes = document.querySelectorAll('input[name="fb-rec-issue"]');

  var errorBanner = document.getElementById('error-banner');
  var extractingIndicator = document.getElementById('extracting-indicator');

  var historyList = document.getElementById('history-list');
  var clearHistoryBtn = document.getElementById('clear-history-btn');
  var HISTORY_KEY = 'sitemap_history';
  var HISTORY_MAX = 50;

  var extractedStyles = null;
  var stylesReady = false;
  var extractedRecsStyles = null;
  var recsCardBody = '';
  var recsAvailable = false;

  var artifacts = {
    sitemap: { value: '', state: 'empty', label: 'Sitemap JS' },
    hero: { value: '', state: 'empty', label: 'Hero Experience Template' },
    rec: { value: '', state: 'empty', label: 'Recs Experience Template' },
  };

  var openButtons = { sitemap: openSitemapBtn, hero: openHeroBtn, rec: openRecBtn };
  var copyButtons = { sitemap: copyBtn, hero: copyHeroBtn, rec: copyRecBtn };

  var currentModalArtifact = null;

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

function setRecStatus(message) {
    if (!message) {
      recStatusNote.hidden = true;
      recStatusNote.textContent = '';
      return;
    }
    recStatusNote.textContent = message;
    recStatusNote.hidden = false;
  }

  function heroInputsReady() {
    return targetSelectorInput.value.trim() && targetHtmlInput.value.trim();
  }

  function recsInputsReady() {
    return recContainerSelectorInput.value.trim()
      && recContainerHtmlInput.value.trim()
      && recHtmlInput.value.trim();
  }

  function refreshSectionButtons() {
    var ready = heroInputsReady();
    if (artifacts.sitemap.state !== 'generating') generateSitemapBtn.disabled = !ready;
    if (artifacts.hero.state !== 'generating') generateHeroBtn.disabled = !ready;
    if (artifacts.rec.state !== 'generating') generateRecBtn.disabled = !recsInputsReady();
  }

  var STATUS_LABELS = {
    empty: 'Not generated',
    generating: 'Generating…',
    ready: 'Ready',
    failed: 'Failed',
  };

  function setArtifactState(key, state, value) {
    var record = artifacts[key];
    record.state = state;
    if (typeof value === 'string') record.value = value;

    var row = document.querySelector('.artifact-row[data-artifact="' + key + '"]');
    if (row) {
      var chip = row.querySelector('.artifact-status');
      chip.dataset.state = state;
      chip.querySelector('.status-text').textContent = STATUS_LABELS[state];
    }

    var hasValue = !!record.value;
    openButtons[key].disabled = !hasValue;
    copyButtons[key].disabled = !hasValue;
  }

  async function extractStyles(pageUrl, targetSelector, mode) {
    var response = await fetch('/extract-styles', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pageUrl: pageUrl,
        targetSelector: targetSelector,
        mode: mode || 'hero',
      }),
    });
    var data = await response.json().catch(function () { return {}; });
    if (!response.ok) throw new Error(data.error || 'Style extraction failed.');
    return data.extractedStyles || null;
  }

  async function extractHeroAndRecsStyles(pageUrl, heroSelector, recsCardSelector) {
    extractingIndicator.hidden = false;
    stylesReady = false;
    try {
      var heroPromise = extractStyles(pageUrl, heroSelector, 'hero');
      var recsPromise = recsCardSelector
        ? extractStyles(pageUrl, recsCardSelector, 'recs').catch(function () { return null; })
        : Promise.resolve(null);
      var results = await Promise.all([heroPromise, recsPromise]);
      extractedStyles = results[0];
      extractedRecsStyles = results[1];
      stylesReady = true;
    } finally {
      extractingIndicator.hidden = true;
    }
  }

  function applyRecsResult(recs) {
    if (recs && recs.containerSelector && recs.cardSelector) {
      recContainerSelectorInput.value = recs.containerSelector;
      recContainerHtmlInput.value = recs.containerOuterHtml || '';
      recHtmlInput.value = recs.exemplarOuterHtml || '';
      recsAvailable = true;
      setRecStatus('');
    } else {
      recContainerSelectorInput.value = '';
      recContainerHtmlInput.value = '';
      recHtmlInput.value = '';
      recsAvailable = false;
      setRecStatus('No recommendations section detected — fill in the fields below to generate.');
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
        applyRecsResult(null);
        refreshSectionButtons();
        return;
      }

      targetSelectorInput.value = data.selector || '';
      targetHtmlInput.value = data.outerHtml || '';
      detectedFields.hidden = false;

      applyRecsResult(data.recs);

      try {
        await extractHeroAndRecsStyles(
          pageUrl,
          targetSelectorInput.value.trim(),
          recsAvailable ? recContainerSelectorInput.value.trim() : null
        );
      } catch (extractErr) {
        showError(extractErr.message || 'Style extraction failed.');
      }
      refreshSectionButtons();
    } catch (err) {
      showError('Could not access this site automatically. Enter the CSS selector and element HTML below.');
      detectedFields.hidden = false;
      applyRecsResult(null);
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
    setArtifactState('sitemap', 'generating');
    setBtnLoading(generateSitemapBtn, true);
    try {
      var response = await fetch('/assemble-sitemap', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          heroSelector: targetSelectorInput.value.trim(),
          recSelector: recContainerSelectorInput.value.trim(),
        }),
      });
      var data = await response.json().catch(function () { return {}; });
      if (!response.ok) {
        setArtifactState('sitemap', 'failed');
        showError(data.error || 'Sitemap assembly failed.');
        return;
      }
      setArtifactState('sitemap', 'ready', data.sitemap || '');
      addHistoryEntry(pageUrlInput.value.trim(), { sitemap: data.sitemap });
    } catch (err) {
      setArtifactState('sitemap', 'failed');
      showError('Network error during sitemap assembly. Try again.');
    } finally {
      setBtnLoading(generateSitemapBtn, false);
      refreshSectionButtons();
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

    setArtifactState('hero', 'generating');
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
        setArtifactState('hero', 'failed');
        if (response.status >= 502 && response.status <= 504) showError(TIMEOUT_MSG);
        else showError(data.error || 'Hero generation failed (' + response.status + ').');
        return;
      }
      if (!data.heroTemplate) {
        setArtifactState('hero', 'failed');
        showError('Hero generation returned empty output.');
        return;
      }
      setArtifactState('hero', 'ready', data.heroTemplate);
      addHistoryEntry(pageUrl, { heroTemplate: data.heroTemplate });
    } catch (err) {
      setArtifactState('hero', 'failed');
      showError(err.name === 'TypeError' ? TIMEOUT_MSG : 'Network error during hero generation. Try again.');
    } finally {
      setBtnLoading(generateHeroBtn, false);
      refreshSectionButtons();
    }
  }

  async function useDefaultHeroTemplate() {
    clearError();
    setArtifactState('hero', 'generating');
    try {
      var response = await fetch('/hero-template', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
      var data = await response.json().catch(function () { return {}; });
      if (!response.ok || !data.heroTemplate) { setArtifactState('hero', 'failed'); showError('Default hero template failed.'); return; }
      setArtifactState('hero', 'ready', data.heroTemplate);
      addHistoryEntry(pageUrlInput.value.trim(), { heroTemplate: data.heroTemplate });
    } catch (err) {
      setArtifactState('hero', 'failed');
      showError('Network error loading default hero template.');
    }
  }

  async function useDefaultRecTemplate() {
    clearError();
    setArtifactState('rec', 'generating');
    try {
      var response = await fetch('/recommendations-template', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
      var data = await response.json().catch(function () { return {}; });
      if (!response.ok || !data.recTemplate) { setArtifactState('rec', 'failed'); showError('Default recs template failed.'); return; }
      recsCardBody = data.recTemplate;
      setArtifactState('rec', 'ready', data.recTemplate);
      addHistoryEntry(pageUrlInput.value.trim(), { recTemplate: data.recTemplate });
    } catch (err) {
      setArtifactState('rec', 'failed');
      showError('Network error loading default recs template.');
    }
  }

  async function generateRecommendations() {
    clearError();
    setArtifactState('rec', 'generating');
    setBtnLoading(generateRecBtn, true);

    var pageUrl = pageUrlInput.value.trim();
    var containerHtml = recContainerHtmlInput.value;
    var cardHtml = recHtmlInput.value;

    try {
      var response = await fetch('/generate-recs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pageUrl: pageUrl,
          containerHtml: containerHtml,
          cardHtml: cardHtml,
          extractedStyles: extractedRecsStyles,
        }),
      });
      var data = await response.json().catch(function () { return {}; });
      if (!response.ok) {
        setArtifactState('rec', 'failed');
        if (response.status >= 502 && response.status <= 504) showError(TIMEOUT_MSG);
        else showError(data.error || 'Recs generation failed (' + response.status + ').');
        return;
      }
      if (!data.recsTemplate) {
        setArtifactState('rec', 'failed');
        showError('Recs generation returned empty output.');
        return;
      }
      recsCardBody = data.cardBody || '';
      setArtifactState('rec', 'ready', data.recsTemplate);
      addHistoryEntry(pageUrl, { recTemplate: data.recsTemplate });
    } catch (err) {
      setArtifactState('rec', 'failed');
      showError(err.name === 'TypeError' ? TIMEOUT_MSG : 'Network error during recommendations generation. Try again.');
    } finally {
      setBtnLoading(generateRecBtn, false);
      refreshSectionButtons();
    }
  }

  async function regenerateRecsWithFeedback() {
    clearError();
    var issues = getCheckedRecIssues();
    var note = feedbackNote.value.trim();
    if (issues.length === 0 && !note) {
      showError('Select an issue or provide feedback text.');
      return;
    }
    if (!recsCardBody) {
      showError('No previous recs card body to refine — regenerate from the main panel first.');
      return;
    }

    setBtnLoading(regenerateBtn, true);
    setArtifactState('rec', 'generating');
    try {
      var response = await fetch('/regenerate-recs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          containerHtml: recContainerHtmlInput.value,
          cardHtml: recHtmlInput.value,
          extractedStyles: extractedRecsStyles,
          previousTemplate: recsCardBody,
          issues: issues,
          feedbackNote: note,
        }),
      });
      var data = await response.json().catch(function () { return {}; });
      if (!response.ok) {
        setArtifactState('rec', 'failed');
        if (response.status >= 502 && response.status <= 504) showError(TIMEOUT_MSG);
        else showError(data.error || 'Recs regeneration failed (' + response.status + ').');
        return;
      }
      if (!data.recsTemplate) {
        setArtifactState('rec', 'failed');
        showError('Recs regeneration returned empty output.');
        return;
      }
      recsCardBody = data.cardBody || '';
      setArtifactState('rec', 'ready', data.recsTemplate);
      addHistoryEntry(pageUrlInput.value.trim(), { recTemplate: data.recsTemplate });
      modalCode.value = data.recsTemplate;
      switchModalTab('code');
      resetFeedbackForm();
    } catch (err) {
      setArtifactState('rec', 'failed');
      showError(err.name === 'TypeError' ? TIMEOUT_MSG : 'Network error during regeneration. Try again.');
    } finally {
      setBtnLoading(regenerateBtn, false);
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
    setArtifactState('hero', 'generating');
    try {
      var response = await fetch('/regenerate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pageUrl: pageUrlInput.value.trim(),
          targetSelector: targetSelectorInput.value.trim(),
          targetHtml: targetHtmlInput.value,
          extractedStyles: extractedStyles,
          previousOutput: artifacts.hero.value,
          issues: issues,
          feedbackNote: note,
          customerName: customerNameInput.value.trim(),
        }),
      });
      var data = await response.json().catch(function () { return {}; });
      if (!response.ok) {
        setArtifactState('hero', 'failed');
        if (response.status >= 502 && response.status <= 504) showError(TIMEOUT_MSG);
        else showError(data.error || 'Regeneration failed (' + response.status + ').');
        return;
      }
      if (!data.heroTemplate) {
        setArtifactState('hero', 'failed');
        showError('Regeneration returned empty output.');
        return;
      }
      setArtifactState('hero', 'ready', data.heroTemplate);
      addHistoryEntry(pageUrlInput.value.trim(), { heroTemplate: data.heroTemplate });
      modalCode.value = data.heroTemplate;
      switchModalTab('code');
      resetFeedbackForm();
    } catch (err) {
      setArtifactState('hero', 'failed');
      showError(err.name === 'TypeError' ? TIMEOUT_MSG : 'Network error during regeneration. Try again.');
    } finally {
      setBtnLoading(regenerateBtn, false);
    }
  }

  function getCheckedIssues() {
    var issues = [];
    heroIssueCheckboxes.forEach(function (cb) { if (cb.checked) issues.push(cb.value); });
    return issues;
  }

  function getCheckedRecIssues() {
    var issues = [];
    recIssueCheckboxes.forEach(function (cb) { if (cb.checked) issues.push(cb.value); });
    return issues;
  }

  function activeIssueCount() {
    return currentModalArtifact === 'rec' ? getCheckedRecIssues().length : getCheckedIssues().length;
  }

  function updateRegenerateEnabled() {
    regenerateBtn.disabled = activeIssueCount() === 0 && !feedbackNote.value.trim();
  }

  function resetFeedbackForm() {
    feedbackNote.value = '';
    heroIssueCheckboxes.forEach(function (cb) { cb.checked = false; });
    recIssueCheckboxes.forEach(function (cb) { cb.checked = false; });
    regenerateBtn.disabled = true;
  }

  function setRegenerateLabel() {
    var labelEl = regenerateBtn.querySelector('.btn-label');
    if (!labelEl) return;
    labelEl.textContent = currentModalArtifact === 'rec' ? 'Regenerate Recs' : 'Regenerate Hero';
  }

  function switchModalTab(tab) {
    modalTabButtons.forEach(function (btn) {
      btn.classList.toggle('is-active', btn.dataset.tab === tab);
    });
    var refineActive = tab === 'refine';
    var isRec = currentModalArtifact === 'rec';

    modalCodePanel.hidden = tab !== 'code';
    modalRefinePanel.hidden = !refineActive;
    modalCopyBtn.hidden = tab !== 'code';
    regenerateBtn.hidden = !refineActive;

    heroFeedbackChecks.hidden = isRec;
    recFeedbackChecks.hidden = !isRec;
    setRegenerateLabel();
    updateRegenerateEnabled();
  }

  function openModal(key) {
    var record = artifacts[key];
    if (!record.value) return;
    currentModalArtifact = key;
    modalHeading.textContent = record.label;
    modalCode.value = record.value;

    var isRec = key === 'rec';
    heroFeedbackChecks.hidden = isRec;
    recFeedbackChecks.hidden = !isRec;

    var showTabs = key === 'hero' || (key === 'rec' && recsCardBody);
    modalTabs.hidden = !showTabs;
    if (showTabs) {
      switchModalTab('code');
    } else {
      modalCodePanel.hidden = false;
      modalRefinePanel.hidden = true;
      modalCopyBtn.hidden = false;
      regenerateBtn.hidden = true;
    }

    modal.hidden = false;
    document.body.classList.add('modal-open');
  }

  function dispatchRegenerate() {
    if (currentModalArtifact === 'rec') {
      regenerateRecsWithFeedback();
    } else {
      regenerateHeroWithFeedback();
    }
  }

  function closeModal() {
    modal.hidden = true;
    document.body.classList.remove('modal-open');
    currentModalArtifact = null;
    resetFeedbackForm();
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
  defaultHeroBtn.addEventListener('click', useDefaultHeroTemplate);
  defaultRecBtn.addEventListener('click', useDefaultRecTemplate);
  openSitemapBtn.addEventListener('click', function () { openModal('sitemap'); });
  openHeroBtn.addEventListener('click', function () { openModal('hero'); });
  openRecBtn.addEventListener('click', function () { openModal('rec'); });
  regenerateBtn.addEventListener('click', dispatchRegenerate);

  modalTabButtons.forEach(function (btn) {
    btn.addEventListener('click', function () { switchModalTab(btn.dataset.tab); });
  });

  modal.addEventListener('click', function (e) {
    if (e.target.hasAttribute('data-close-modal')) closeModal();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !modal.hidden) closeModal();
  });

  heroIssueCheckboxes.forEach(function (cb) { cb.addEventListener('change', updateRegenerateEnabled); });
  recIssueCheckboxes.forEach(function (cb) { cb.addEventListener('change', updateRegenerateEnabled); });
  feedbackNote.addEventListener('input', updateRegenerateEnabled);

  targetSelectorInput.addEventListener('input', refreshSectionButtons);
  targetHtmlInput.addEventListener('input', refreshSectionButtons);

  recContainerSelectorInput.addEventListener('input', refreshSectionButtons);
  recContainerHtmlInput.addEventListener('input', refreshSectionButtons);
  recHtmlInput.addEventListener('input', refreshSectionButtons);

  function copyAction(btn, getValue) {
    btn.addEventListener('click', async function () {
      var value = getValue();
      if (!value) return;
      try {
        await navigator.clipboard.writeText(value);
        var original = btn.textContent;
        btn.textContent = 'Copied!';
        var wasDisabled = btn.disabled;
        btn.disabled = true;
        setTimeout(function () {
          btn.textContent = original;
          btn.disabled = wasDisabled || !getValue();
        }, 1500);
      } catch (e) {
        showError('Could not copy to clipboard.');
      }
    });
  }
  copyAction(copyBtn, function () { return artifacts.sitemap.value; });
  copyAction(copyHeroBtn, function () { return artifacts.hero.value; });
  copyAction(copyRecBtn, function () { return artifacts.rec.value; });
  copyAction(modalCopyBtn, function () {
    return currentModalArtifact ? artifacts[currentModalArtifact].value : '';
  });

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
        + '<span class="history-brand" title="' + entry.brand + '">' + entry.brand + '</span>'
        + '<span class="history-url" title="' + entry.url + '">' + entry.url + '</span>'
        + '<span class="history-time">' + timeAgo(entry.timestamp) + '</span>'
        + '</div>'
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
      if (entry.sitemap) setArtifactState('sitemap', 'ready', entry.sitemap);
      if (entry.heroTemplate) setArtifactState('hero', 'ready', entry.heroTemplate);
      if (entry.recTemplate) setArtifactState('rec', 'ready', entry.recTemplate);
      document.querySelector('[aria-labelledby="output-heading"]').scrollIntoView({ behavior: 'smooth', block: 'center' });
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

  var schemaGuideModal = document.getElementById('schema-guide-modal');
  var schemaGuideContent = document.getElementById('schema-guide-content');

  var SCHEMA_DATA = {
    hero: {
      schema: 'Simple Hero',
      variables: [
        { label: 'BackgroundImageUrl', api: 'BackgroundImageUrl', default: 'Attributes > BackgroundImageUrl' },
        { label: 'Header',             api: 'Header',             default: 'Attributes > Header' },
        { label: 'Subheader',          api: 'Subheader',          default: 'Attributes > Subheader' },
        { label: 'CallToActionText',   api: 'CallToActionText',   default: 'Attributes > CallToActionText' },
        { label: 'CallToActionUrl',    api: 'CallToActionUrl',    default: 'Attributes > CallToActionUrl' },
      ]
    },
    recs: {
      schema: 'Recommendations - Goods Product',
      variables: [
        { label: 'image',   api: 'image',   default: 'Goods Product > ImageUrl' },
        { label: 'name',    api: 'name',    default: 'Goods Product > Product Name' },
        { label: 'linkUrl', api: 'linkUrl', default: 'Goods Product > LinkURL' },
      ]
    }
  };

  function openSchemaGuide(type) {
    var data = SCHEMA_DATA[type];
    if (!data) return;
    var rows = data.variables.map(function (v) {
      return '<tr><td><code>' + v.label + '</code></td><td><code>' + v.api + '</code></td><td>' + v.default + '</td></tr>';
    }).join('');
    schemaGuideContent.innerHTML =
      '<p class="schema-guide-schema">Content Schema: <strong>' + data.schema + '</strong></p>'
      + '<table class="schema-guide-table">'
      + '<thead><tr><th>Label</th><th>API Name</th><th>Default Value</th></tr></thead>'
      + '<tbody>' + rows + '</tbody>'
      + '</table>';
    schemaGuideModal.hidden = false;
    document.body.classList.add('modal-open');
  }

  function closeSchemaGuide() {
    schemaGuideModal.hidden = true;
    document.body.classList.remove('modal-open');
  }

  document.querySelectorAll('.schema-guide-link').forEach(function (btn) {
    btn.addEventListener('click', function () { openSchemaGuide(btn.dataset.schema); });
  });

  schemaGuideModal.addEventListener('click', function (e) {
    if (e.target.hasAttribute('data-close-schema-modal')) closeSchemaGuide();
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !schemaGuideModal.hidden) closeSchemaGuide();
  });

})();
