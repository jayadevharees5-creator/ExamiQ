/* ============================================================
   SMART QGEN — Application Logic
   ============================================================
   Two generation modes:
   1. PDF/RAG — Upload material, configure, generate from document
   2. Knowledge — Curriculum Studio + Algorithmic Problem Studio
   ============================================================ */

(function () {
  'use strict';

  // ── State ──────────────────────────────────────────────────
  const state = {
    user: null,
    token: null,
    currentPage: 'dashboard',
    currentStep: 1,
    genMode: 'pdf',          // 'pdf' or 'knowledge'
    studioTab: 'coursework', // 'coursework' or 'algorithmic'
    uploadedFiles: [],
    userStudyMaterials: [],
    selectedMaterialId: null,
    detectedUnits: [],
    generatedQuestions: [],
    generatedDocuments: [],
    editingIndex: -1,
    config: {
      subject: '', unit: '', topic: '', count: 10,
      questionTypes: ['Multiple Choice Questions (MCQ)'],
      difficulty: 'Medium',
      blooms: ['Remember', 'Understand'],
      marks: '100', duration: '1 Hour', instructions: ''
    }
  };

  // ── Helpers ────────────────────────────────────────────────
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);
  const show = (el) => { if (el) el.hidden = false; };
  const hide = (el) => { if (el) el.hidden = true; };

  function formatBytes(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
  }

  function formatDate(d) {
    const date = d ? new Date(d) : new Date();
    return date.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
  }

  function getGreeting() {
    const h = new Date().getHours();
    if (h < 12) return 'Good Morning';
    if (h < 17) return 'Good Afternoon';
    return 'Good Evening';
  }

  async function api(url, options = {}) {
    const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
    if (state.token) headers['Authorization'] = `Bearer ${state.token}`;
    const res = await fetch(url, { ...options, headers });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Request failed');
    return data;
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function showToast(message, type = 'success', el = null) {
    const toast = el || $('#global-toast');
    toast.textContent = message;
    toast.className = (el ? 'toast' : 'global-toast') + ` toast--${type}`;
    show(toast);
    setTimeout(() => hide(toast), 4000);
  }

  // ── Navigation ─────────────────────────────────────────────
  function navigateTo(page) {
    state.currentPage = page;
    $$('.nav-link').forEach(l => l.classList.toggle('nav-link--active', l.dataset.page === page));
    $$('.page-view').forEach(v => v.classList.toggle('page-view--active', v.id === `view-${page}`));
    closeMenu();
    if (page === 'dashboard') initDashboard();
    if (page === 'history') renderHistory();
    if (page === 'generate') {
      const activeStep = document.querySelector('.step-content.step-content--active');
      if (state.genMode === 'pdf') {
        const stepNum = (!activeStep || activeStep.id === 'step-3' || activeStep.id === 'step-4') ? 1 : state.currentStep;
        if (typeof setGenMode === 'function') {
          setGenMode('pdf', stepNum);
        } else {
          loadUserStudyMaterials();
        }
      } else {
        if (!activeStep || activeStep.id === 'step-3' || activeStep.id === 'step-4') {
          if (typeof setGenMode === 'function') setGenMode('knowledge');
        }
      }
    }
    if (page === 'admin') initAdminDashboard();
  }

  // ── Cache & Session State Reset ───────────────────────────
  function clearUserState() {
    state.user = null;
    state.token = null;
    state.uploadedFiles = [];
    state.userStudyMaterials = [];
    state.selectedMaterialId = null;
    state.detectedUnits = [];
    state.generatedQuestions = [];
    state.generatedDocuments = [];
    state.editingIndex = -1;
    state.config = {
      subject: '', unit: '', topic: '', count: 10,
      questionTypes: ['Multiple Choice Questions (MCQ)'],
      difficulty: 'Medium',
      blooms: ['Remember', 'Understand'],
      marks: '100', duration: '1 Hour', instructions: ''
    };

    try {
      sessionStorage.clear();
      localStorage.clear();
    } catch (e) {}

    // Reset forms
    $('#login-form')?.reset();
    $('#register-form')?.reset();
    $('#forgot-form')?.reset();

    // Reset Admin Nav visibility
    const adminLink = $('#nav-admin-link');
    if (adminLink) adminLink.style.display = 'none';
    const ddAdminBtn = $('#dd-admin-btn');
    if (ddAdminBtn) ddAdminBtn.style.display = 'none';

    // Clear processed study materials UI
    const procList = $('#processed-materials-list');
    if (procList) procList.innerHTML = '';
    hide($('#user-processed-materials'));

    // Reset generation inputs
    if ($('#cfg-subject')) $('#cfg-subject').value = '';
    if ($('#cfg-unit')) $('#cfg-unit').value = '';
    if ($('#cfg-topic')) $('#cfg-topic').value = '';
    if ($('#kb-topic')) $('#kb-topic').value = '';
    if ($('#dsa-topic')) $('#dsa-topic').value = '';
    if ($('#instructions')) $('#instructions').value = '';
    if ($('#kb-notes')) $('#kb-notes').value = '';
    if ($('#dsa-notes')) $('#dsa-notes').value = '';

    // Clear uploaded files in UI
    const filesList = $('#files-list');
    if (filesList) filesList.innerHTML = '';
    const uploadedFiles = $('#uploaded-files');
    if (uploadedFiles) uploadedFiles.innerHTML = '';

    // Reset Dashboard statistics & empty states
    if ($('#stat-papers')) $('#stat-papers').textContent = '0';
    if ($('#stat-questions')) $('#stat-questions').textContent = '0';
    if ($('#stat-subjects')) $('#stat-subjects').textContent = '0';
    if ($('#stat-recent')) $('#stat-recent').textContent = '0';
    if ($('#recent-papers-list')) $('#recent-papers-list').innerHTML = '';
    show($('#dashboard-empty'));

    // Clear history view
    const histGrid = $('#history-grid');
    if (histGrid) histGrid.innerHTML = '';
    show($('#history-empty'));

    // Clear live preview & question containers
    const previewEl = $('#live-preview-questions');
    if (previewEl) previewEl.innerHTML = '<div class="live-preview-empty">Select or enter configuration on the left to see live preview.</div>';
    const kbPreviewEl = $('#kb-live-preview-questions');
    if (kbPreviewEl) kbPreviewEl.innerHTML = '<div class="live-preview-empty">Configure parameters to see dynamic live preview.</div>';
    const questionsContainer = $('#questions-container');
    if (questionsContainer) questionsContainer.innerHTML = '';
    const paperBody = $('#paper-body');
    if (paperBody) paperBody.innerHTML = '';
    if ($('#paper-title')) $('#paper-title').textContent = 'Examination Paper Preview';
  }

  // ── Login & Registration ──────────────────────────────────
  function initLogin() {
    const loginCard = $('#card-signin');
    const registerCard = $('#card-register');
    const forgotCard = $('#card-forgot');
    const form = $('#login-form');
    const emailInput = $('#login-email');
    const pwInput = $('#login-password');

    // Toggle between Sign In, Register, and Forgot Password
    $('#to-register-link')?.addEventListener('click', (e) => {
      e.preventDefault();
      clearUserState();
      hide(loginCard);
      hide(forgotCard);
      show(registerCard);
    });

    $('#to-signin-link')?.addEventListener('click', (e) => {
      e.preventDefault();
      clearUserState();
      hide(registerCard);
      hide(forgotCard);
      show(loginCard);
    });

    $('#forgot-pw-link')?.addEventListener('click', (e) => {
      e.preventDefault();
      hide(loginCard);
      hide(registerCard);
      show(forgotCard);
    });

    $('#forgot-to-signin-link')?.addEventListener('click', (e) => {
      e.preventDefault();
      hide(forgotCard);
      hide(registerCard);
      show(loginCard);
    });

    $('#toggle-pw')?.addEventListener('click', () => {
      pwInput.type = pwInput.type === 'password' ? 'text' : 'password';
    });

    // Login Submission
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const email = emailInput.value.trim();
      const password = pwInput.value.trim();
      let valid = true;

      if (!email) {
        emailInput.classList.add('is-error');
        $('#login-email-error').textContent = 'Please enter your ID or email';
        valid = false;
      } else {
        emailInput.classList.remove('is-error');
        $('#login-email-error').textContent = '';
      }
      if (!password) {
        pwInput.classList.add('is-error');
        $('#login-password-error').textContent = 'Please enter your password';
        valid = false;
      } else {
        pwInput.classList.remove('is-error');
        $('#login-password-error').textContent = '';
      }
      if (!valid) return;

      const btn = $('#login-btn');
      btn.querySelector('.btn__text').hidden = true;
      show(btn.querySelector('.btn__loader'));
      btn.disabled = true;

      try {
        const data = await api('/api/login', {
          method: 'POST', body: JSON.stringify({ username: email, password })
        });
        clearUserState();
        state.user = data.user;
        state.token = data.token;
        enterApp();
      } catch (err) {
        showToast(err.message || 'Login failed', 'error', $('#login-toast'));
      } finally {
        btn.querySelector('.btn__text').hidden = false;
        hide(btn.querySelector('.btn__loader'));
        btn.disabled = false;
      }
    });

    emailInput.addEventListener('input', () => { emailInput.classList.remove('is-error'); $('#login-email-error').textContent = ''; });
    pwInput.addEventListener('input', () => { pwInput.classList.remove('is-error'); $('#login-password-error').textContent = ''; });

    // Registration Submission
    const regForm = $('#register-form');
    if (regForm) {
      regForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const fullname = $('#reg-fullname').value.trim();
        const username = $('#reg-username').value.trim();
        const role = $('#reg-role').value;
        const password = $('#reg-password').value.trim();
        let valid = true;

        if (!fullname) {
          $('#reg-fullname').classList.add('is-error');
          $('#reg-fullname-error').textContent = 'Please enter your full name';
          valid = false;
        } else {
          $('#reg-fullname').classList.remove('is-error');
          $('#reg-fullname-error').textContent = '';
        }

        if (!username || username.length < 3) {
          $('#reg-username').classList.add('is-error');
          $('#reg-username-error').textContent = 'Username must be at least 3 characters';
          valid = false;
        } else {
          $('#reg-username').classList.remove('is-error');
          $('#reg-username-error').textContent = '';
        }

        if (!password || password.length < 4) {
          $('#reg-password').classList.add('is-error');
          $('#reg-password-error').textContent = 'Password must be at least 4 characters';
          valid = false;
        } else {
          $('#reg-password').classList.remove('is-error');
          $('#reg-password-error').textContent = '';
        }

        if (!valid) return;

        const regBtn = $('#reg-btn');
        regBtn.querySelector('.btn__text').hidden = true;
        show(regBtn.querySelector('.btn__loader'));
        regBtn.disabled = true;

        try {
          const res = await api('/api/register', {
            method: 'POST',
            body: JSON.stringify({
              username: username,
              password: password,
              role: role,
              full_name: fullname
            })
          });

          showToast('Account created successfully! Signing in…', 'success', $('#reg-toast'));

          const loginData = await api('/api/login', {
            method: 'POST',
            body: JSON.stringify({ username: username, password: password })
          });
          clearUserState();
          state.user = loginData.user;
          state.token = loginData.token;
          setTimeout(() => enterApp(), 600);

        } catch (err) {
          showToast(err.message || 'Registration failed', 'error', $('#reg-toast'));
        } finally {
          regBtn.querySelector('.btn__text').hidden = false;
          hide(regBtn.querySelector('.btn__loader'));
          regBtn.disabled = false;
        }
      });

      $('#reg-fullname').addEventListener('input', () => { $('#reg-fullname').classList.remove('is-error'); $('#reg-fullname-error').textContent = ''; });
      $('#reg-username').addEventListener('input', () => { $('#reg-username').classList.remove('is-error'); $('#reg-username-error').textContent = ''; });
      $('#reg-password').addEventListener('input', () => { $('#reg-password').classList.remove('is-error'); $('#reg-password-error').textContent = ''; });
    }

    // Forgot Password Submission
    const forgotForm = $('#forgot-form');
    if (forgotForm) {
      forgotForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const username = $('#forgot-username').value.trim();
        const newPassword = $('#forgot-password').value.trim();
        const confirmPassword = $('#forgot-confirm').value.trim();
        let valid = true;

        if (!username) {
          $('#forgot-username').classList.add('is-error');
          $('#forgot-username-error').textContent = 'Please enter your username';
          valid = false;
        } else if (username.toLowerCase() === 'admin') {
          $('#forgot-username').classList.add('is-error');
          $('#forgot-username-error').textContent = 'The admin password cannot be changed here. It can only be changed in the server .env file.';
          valid = false;
        } else {
          $('#forgot-username').classList.remove('is-error');
          $('#forgot-username-error').textContent = '';
        }

        if (!newPassword || newPassword.length < 4) {
          $('#forgot-password').classList.add('is-error');
          $('#forgot-password-error').textContent = 'Password must be at least 4 characters';
          valid = false;
        } else {
          $('#forgot-password').classList.remove('is-error');
          $('#forgot-password-error').textContent = '';
        }

        if (newPassword !== confirmPassword) {
          $('#forgot-confirm').classList.add('is-error');
          $('#forgot-confirm-error').textContent = 'Passwords do not match';
          valid = false;
        } else {
          $('#forgot-confirm').classList.remove('is-error');
          $('#forgot-confirm-error').textContent = '';
        }

        if (!valid) return;

        const forgotBtn = $('#forgot-btn');
        forgotBtn.querySelector('.btn__text').hidden = true;
        show(forgotBtn.querySelector('.btn__loader'));
        forgotBtn.disabled = true;

        try {
          const res = await api('/api/forgot-password', {
            method: 'POST',
            body: JSON.stringify({
              username: username,
              new_password: newPassword
            })
          });

          showToast(res.message || 'Password reset successfully! Please sign in.', 'success', $('#login-toast'));
          hide(forgotCard);
          show(loginCard);
          $('#login-email').value = username;
          $('#login-password').value = '';
          $('#login-password').focus();
        } catch (err) {
          showToast(err.message || 'Password reset failed', 'error', $('#forgot-toast'));
        } finally {
          forgotBtn.querySelector('.btn__text').hidden = false;
          hide(forgotBtn.querySelector('.btn__loader'));
          forgotBtn.disabled = false;
        }
      });

      $('#forgot-username')?.addEventListener('input', () => { $('#forgot-username').classList.remove('is-error'); $('#forgot-username-error').textContent = ''; });
      $('#forgot-password')?.addEventListener('input', () => { $('#forgot-password').classList.remove('is-error'); $('#forgot-password-error').textContent = ''; });
      $('#forgot-confirm')?.addEventListener('input', () => { $('#forgot-confirm').classList.remove('is-error'); $('#forgot-confirm-error').textContent = ''; });
    }
  }

  function enterApp() {
    hide($('#page-login'));
    show($('#app-shell'));
    const name = state.user?.full_name || state.user?.username || 'Faculty';
    const initials = name.charAt(0).toUpperCase();
    $('#user-display-name').textContent = name;
    $('#user-avatar').textContent = initials;
    $('#dd-avatar').textContent = initials;
    $('#dd-name').textContent = name;
    $('#dd-role').textContent = state.user?.role || 'Faculty';
    $('#hero-greeting').textContent = `${getGreeting()}, ${name.split(' ')[0]}`;

    // Admin-specific nav visibility
    const isAdmin = (state.user?.role || '').toLowerCase() === 'admin';
    const adminLink = $('#nav-admin-link');
    if (adminLink) adminLink.style.display = isAdmin ? 'inline-flex' : 'none';
    const ddAdminBtn = $('#dd-admin-btn');
    if (ddAdminBtn) ddAdminBtn.style.display = isAdmin ? 'flex' : 'none';

    navigateTo('dashboard');
    loadStatus();
  }

  // ── App Shell ──────────────────────────────────────────────
  function initAppShell() {
    $$('.nav-link').forEach(l => l.addEventListener('click', (e) => { e.preventDefault(); navigateTo(l.dataset.page); }));
    $('#hamburger-btn').addEventListener('click', toggleMenu);
    $('#mobile-nav-overlay').addEventListener('click', closeMenu);
    $('#profile-btn').addEventListener('click', (e) => { e.stopPropagation(); const dd = $('#profile-dropdown'); dd.hidden = !dd.hidden; });
    document.addEventListener('click', () => hide($('#profile-dropdown')));
    $('#dd-admin-btn')?.addEventListener('click', () => {
      hide($('#profile-dropdown'));
      navigateTo('admin');
    });
    $('#logout-btn').addEventListener('click', async () => {
      try { await api('/api/clear-session', { method: 'POST' }); } catch(e) {}
      clearUserState();
      hide($('#app-shell'));
      show($('#page-login'));
      hide($('#card-register'));
      hide($('#card-forgot'));
      show($('#card-signin'));
    });
    $('#hero-generate-btn').addEventListener('click', () => {
      setGenMode('pdf', 1);
      navigateTo('generate');
    });
    $('#view-all-history-btn').addEventListener('click', () => navigateTo('history'));
  }

  function toggleMenu() {
    const links = $('#nav-links'), overlay = $('#mobile-nav-overlay');
    if (links.classList.contains('is-open')) { links.classList.remove('is-open'); hide(overlay); }
    else { links.classList.add('is-open'); show(overlay); }
  }
  function closeMenu() { $('#nav-links').classList.remove('is-open'); hide($('#mobile-nav-overlay')); }

  // ── Dashboard ──────────────────────────────────────────────
  function initDashboard() {
    const name = state.user?.full_name || state.user?.username || 'Faculty';
    $('#hero-greeting').textContent = `${getGreeting()}, ${name.split(' ')[0]}`;
  }

  async function loadStatus() {
    try {
      const data = await api('/api/status');
      state.detectedUnits = data.detected_units || [];
      updateUnitDropdown();
    } catch (e) {}

    try {
      const userParam = state.user?.username ? `?username=${encodeURIComponent(state.user.username)}` : '';
      const data = await api(`/api/generated-documents${userParam}`);
      if (data.success && Array.isArray(data.documents)) {
        state.generatedDocuments = data.documents;
      } else {
        state.generatedDocuments = [];
      }
    } catch (e) {
      state.generatedDocuments = [];
    }

    updateStats();
    renderRecentPapers();
    loadUserStudyMaterials();
  }

  function updateStats() {
    const docs = state.generatedDocuments;
    const totalQ = docs.reduce((s, d) => s + (d.questions?.length || 0), 0);
    const subjects = new Set(docs.map(d => d.subject).filter(Boolean));
    $('#stat-papers').textContent = docs.length;
    $('#stat-questions').textContent = totalQ;
    $('#stat-subjects').textContent = subjects.size;
    $('#stat-recent').textContent = Math.min(docs.length, 5);
  }

  function renderRecentPapers() {
    const list = $('#recent-papers-list');
    const docs = state.generatedDocuments.slice(-5).reverse();
    if (!docs.length) { show($('#dashboard-empty')); return; }
    hide($('#dashboard-empty'));

    list.innerHTML = docs.map(doc => {
      const subject = doc.subject || 'Untitled';
      const qCount = doc.questions?.length || 0;
      const date = formatDate(doc.created_at || doc.generated_at);
      return `<div class="recent-paper-item">
        <div class="recent-paper-item__info">
          <div class="recent-paper-item__icon">
            <svg viewBox="0 0 20 20" fill="none"><rect x="3" y="2" width="14" height="16" rx="2" stroke="currentColor" stroke-width="1.5"/><path d="M7 6h6M7 9h4M7 12h5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>
          </div>
          <div>
            <div class="recent-paper-item__title">${subject}</div>
            <div class="recent-paper-item__meta">${qCount} questions • ${date}</div>
          </div>
        </div>
        <div class="recent-paper-item__actions">
          <button class="btn btn--ghost btn--sm" onclick="SmartQGen.viewPaper('${doc._id || doc.id || ''}')">View</button>
        </div>
      </div>`;
    }).join('');
  }

  // ── Generation Mode Selector ───────────────────────────────
  function setGenMode(mode, targetStep = 1) {
    state.genMode = mode;
    $$('.gen-mode-tab').forEach(b => b.classList.toggle('gen-mode-tab--active', b.dataset.mode === mode));
    $$('.gen-mode-content').forEach(c => c.classList.toggle('gen-mode-content--active', c.id === `mode-${mode}`));

    const stepper = $('#stepper');
    if (mode === 'pdf') {
      if (stepper) stepper.style.display = '';
      if (state._goToStep) {
        state._goToStep(targetStep || 1);
      }
      updateLivePreview();
      loadUserStudyMaterials();
    } else {
      if (stepper) stepper.style.display = 'none';
      $$('.step-content').forEach(sc => sc.classList.remove('step-content--active'));
      updateKbLivePreview();
    }
  }

  function initModeSelector() {
    $$('.gen-mode-tab').forEach(btn => {
      btn.addEventListener('click', () => {
        const mode = btn.dataset.mode;
        const activeStep = document.querySelector('.step-content.step-content--active');
        const activeStepId = activeStep ? activeStep.id : null;
        let stepToTarget = 1;
        if (mode === 'pdf' && (activeStepId === 'step-1' || activeStepId === 'step-2')) {
          stepToTarget = activeStepId === 'step-2' ? 2 : 1;
        }
        setGenMode(mode, stepToTarget);
      });
    });
  }

  // ── Studio Tabs (Coursework / Algorithmic) ─────────────────
  function initStudioTabs() {
    $$('.studio-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        const t = tab.dataset.tab;
        state.studioTab = t;
        $$('.studio-tab').forEach(b => b.classList.toggle('studio-tab--active', b.dataset.tab === t));
        $$('.studio-panel').forEach(p => p.classList.toggle('studio-panel--active', p.id === `panel-${t}`));
        updateKbLivePreview();
      });
    });

    // Suggestion chips
    $$('.suggestion-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        const topic = chip.dataset.topic;
        if (state.studioTab === 'coursework') {
          $('#kb-topic').value = topic;
        } else {
          $('#dsa-topic').value = topic;
        }
        updateKbLivePreview();
      });
    });
  }

  // ── Stepper (PDF mode) ─────────────────────────────────────
  function initStepper() {
    const steps = $$('.stepper__step');

    function goToStep(n) {
      state.currentStep = n;
      steps.forEach((step, i) => {
        const idx = i + 1;
        step.classList.remove('stepper__step--active', 'stepper__step--done');
        if (idx === n) step.classList.add('stepper__step--active');
        else if (idx < n) step.classList.add('stepper__step--done');
      });
      $$('.stepper__connector').forEach((conn, i) => {
        conn.style.background = (i + 1 < n) ? 'var(--success)' : 'var(--border)';
      });
      $$('.step-content').forEach((sc, i) => sc.classList.toggle('step-content--active', i + 1 === n));

      // When going to step 3 or 4, ensure we are viewing the PDF mode content
      // (these steps are inside mode-pdf but we also want them visible from knowledge mode)
    }

    $('#step1-next').addEventListener('click', () => { if (state.uploadedFiles.length) { goToStep(2); updateLivePreview(); } });
    $('#step2-back').addEventListener('click', () => goToStep(1));
    $('#step2-next').addEventListener('click', () => { readConfig(); goToStep(3); generatePdfQuestions(); });
    $('#action-new-paper').addEventListener('click', () => {
      state.generatedQuestions = [];
      if (state.genMode === 'pdf') {
        setGenMode('pdf', 1);
      } else {
        setGenMode('knowledge');
      }
    });

    state._goToStep = goToStep;
  }

  // ── Upload ─────────────────────────────────────────────────
  function initUpload() {
    const zone = $('#upload-zone');
    const fileInput = $('#file-input');
    const filesList = $('#files-list');
    const container = $('#uploaded-files');
    const nextBtn = $('#step1-next');

    zone.addEventListener('click', (e) => { if (e.target.tagName !== 'LABEL') fileInput.click(); });
    zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('is-dragover'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('is-dragover'));
    zone.addEventListener('drop', (e) => { e.preventDefault(); zone.classList.remove('is-dragover'); handleFiles(e.dataTransfer.files); });
    fileInput.addEventListener('change', () => { handleFiles(fileInput.files); fileInput.value = ''; });

    async function handleFiles(files) {
      if (!files.length) return;
      const formData = new FormData();
      Array.from(files).forEach(f => { formData.append('files', f); state.uploadedFiles.push({ id: Date.now() + '_' + f.name, name: f.name, size: f.size, status: 'processing' }); });
      show(container);
      renderFiles();

      try {
        const headers = {};
        if (state.token) headers['Authorization'] = `Bearer ${state.token}`;
        if (state.user?.username) formData.append('username', state.user.username);
        const data = await fetch('/api/upload-pdf', { method: 'POST', body: formData, headers }).then(r => r.json());
        if (data.success) {
          state.detectedUnits = data.detected_units || [];
          updateUnitDropdown();
          state.uploadedFiles.forEach(f => f.status = 'done');
          renderFiles();
          nextBtn.disabled = false;
          if (data.materials && data.materials.length) {
            state.selectedMaterialId = data.materials[0].id;
          }
          await loadUserStudyMaterials();
          showToast(`${data.documents?.length || 1} file(s) processed — ${data.chunk_count} chunks indexed`);
        } else { throw new Error(data.detail || 'Upload failed'); }
      } catch (err) {
        state.uploadedFiles.forEach(f => { if (f.status === 'processing') f.status = 'error'; });
        renderFiles();
        showToast(err.message, 'error');
      }
    }

    function renderFiles() {
      filesList.innerHTML = state.uploadedFiles.map(f => `
        <div class="file-item" data-id="${f.id}">
          <div class="file-item__icon"><svg viewBox="0 0 20 20" fill="none"><rect x="3" y="2" width="14" height="16" rx="2" stroke="currentColor" stroke-width="1.5"/><path d="M7 6h6M7 9h4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg></div>
          <div class="file-item__info">
            <div class="file-item__name">${f.name}</div>
            <div class="file-item__size">${formatBytes(f.size)}</div>
            ${f.status === 'processing' ? '<div class="progress-bar"><div class="progress-bar__fill" style="width:60%"></div></div>' : ''}
          </div>
          <span class="file-item__status file-item__status--${f.status}">${f.status === 'processing' ? 'Processing…' : f.status === 'done' ? 'Ready' : 'Error'}</span>
          <button class="file-item__remove" data-id="${f.id}" title="Remove">✕</button>
        </div>`).join('');

      filesList.querySelectorAll('.file-item__remove').forEach(btn => {
        btn.addEventListener('click', async (e) => {
          e.stopPropagation();
          state.uploadedFiles = state.uploadedFiles.filter(f => f.id !== btn.dataset.id);
          state.selectedMaterialId = null;
          renderFiles();
          if (!state.uploadedFiles.length) {
            hide(container);
            nextBtn.disabled = true;
            try { await api('/api/clear-documents', { method: 'POST' }); } catch (e) {}
          }
          renderUserProcessedMaterials(state.userStudyMaterials);
        });
      });
    }
  }

  // ── User Processed Study Materials ────────────────────────
  async function loadUserStudyMaterials() {
    if (!state.user?.username) return;
    try {
      const data = await api(`/api/user-study-materials?username=${encodeURIComponent(state.user.username)}`);
      if (data.success && Array.isArray(data.materials)) {
        state.userStudyMaterials = data.materials;
        renderUserProcessedMaterials(data.materials);
      }
    } catch (e) {
      console.warn("Could not load user study materials:", e);
    }
  }

  function renderUserProcessedMaterials(materials) {
    const section = $('#user-processed-materials');
    const list = $('#processed-materials-list');
    const badge = $('#processed-count-badge');
    if (!section || !list) return;

    if (!materials || !materials.length) {
      hide(section);
      list.innerHTML = '';
      return;
    }

    show(section);
    if (badge) badge.textContent = `${materials.length} document${materials.length === 1 ? '' : 's'}`;

    list.innerHTML = materials.map(m => {
      const isSelected = state.selectedMaterialId === m.id;
      const chunks = m.chunk_count ? `${m.chunk_count} chunks` : '';
      const pages = m.pages ? `${m.pages} page${m.pages === 1 ? '' : 's'}` : '';
      const date = m.created_at || '';
      const meta = [pages, chunks, date].filter(Boolean).join(' • ');

      return `
        <div class="user-material-item ${isSelected ? 'user-material-item--active' : ''}" data-id="${m.id}">
          <div class="user-material-item__left">
            <div class="user-material-item__icon">📄</div>
            <div>
              <div class="user-material-item__name">${escapeHtml(m.filename)}</div>
              <div class="user-material-item__meta">${escapeHtml(meta)}</div>
            </div>
          </div>
          <div class="user-material-item__actions">
            ${isSelected ? `
              <span class="badge badge--success" style="font-size:0.75rem; padding:4px 8px;">Active</span>
            ` : `
              <button class="btn btn--outline btn--sm select-mat-btn" data-id="${m.id}">
                Select
              </button>
            `}
            <button class="btn btn--ghost btn--sm delete-mat-btn" data-id="${m.id}" title="Delete document" style="color:var(--danger, #EF4444); padding:4px 8px;">
              ✕
            </button>
          </div>
        </div>
      `;
    }).join('');

    list.querySelectorAll('.select-mat-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        selectStudyMaterial(btn.dataset.id);
      });
    });

    list.querySelectorAll('.user-material-item').forEach(card => {
      card.addEventListener('click', (e) => {
        if (e.target.closest('.delete-mat-btn') || e.target.closest('.select-mat-btn')) return;
        selectStudyMaterial(card.dataset.id);
      });
    });

    list.querySelectorAll('.delete-mat-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        deleteStudyMaterial(btn.dataset.id);
      });
    });
  }

  async function selectStudyMaterial(materialId) {
    const mat = (state.userStudyMaterials || []).find(m => m.id === materialId);
    if (!mat) return;

    try {
      showToast(`Loading "${mat.filename}"…`, 'info');
      const userParam = state.user?.username ? `?username=${encodeURIComponent(state.user.username)}` : '';
      const data = await api(`/api/select-study-material/${materialId}${userParam}`, { method: 'POST' });
      if (data.success) {
        state.selectedMaterialId = materialId;
        state.detectedUnits = data.material?.detected_units || [];
        updateUnitDropdown();

        state.uploadedFiles = [{
          id: materialId,
          name: mat.filename,
          size: 0,
          status: 'done'
        }];
        show($('#uploaded-files'));

        const filesList = $('#files-list');
        if (filesList) {
          filesList.innerHTML = `
            <div class="file-item" data-id="${mat.id}">
              <div class="file-item__icon"><svg viewBox="0 0 20 20" fill="none"><rect x="3" y="2" width="14" height="16" rx="2" stroke="currentColor" stroke-width="1.5"/><path d="M7 6h6M7 9h4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg></div>
              <div class="file-item__info">
                <div class="file-item__name">${escapeHtml(mat.filename)}</div>
                <div class="file-item__size">${mat.pages || 1} pages • Ready for questions</div>
              </div>
              <span class="file-item__status file-item__status--done">Ready</span>
              <button class="file-item__remove" data-id="${mat.id}" title="Deselect">✕</button>
            </div>
          `;
          filesList.querySelector('.file-item__remove')?.addEventListener('click', async (e) => {
            e.stopPropagation();
            state.uploadedFiles = [];
            state.selectedMaterialId = null;
            hide($('#uploaded-files'));
            $('#step1-next').disabled = true;
            try { 
              const uParam = state.user?.username ? `?username=${encodeURIComponent(state.user.username)}` : '';
              await api(`/api/clear-documents${uParam}`, { method: 'POST' }); 
            } catch (err) {}
            renderUserProcessedMaterials(state.userStudyMaterials);
          });
        }

        $('#step1-next').disabled = false;

        // Auto-fill subject if currently empty
        if ($('#cfg-subject') && !$('#cfg-subject').value.trim()) {
          const baseName = mat.filename.replace(/\.[^/.]+$/, '').replace(/[-_]/g, ' ');
          $('#cfg-subject').value = baseName;
          state.config.subject = baseName;
        }

        renderUserProcessedMaterials(state.userStudyMaterials);
        showToast(`"${mat.filename}" is active. Questions will be generated from this document alone.`);
      }
    } catch (err) {
      showToast(err.message || 'Failed to select document', 'error');
    }
  }

  async function deleteStudyMaterial(materialId) {
    if (!confirm('Are you sure you want to remove this processed document?')) return;
    try {
      const userParam = state.user?.username ? `?username=${encodeURIComponent(state.user.username)}` : '';
      const data = await api(`/api/user-study-material/${materialId}${userParam}`, { method: 'DELETE' });
      if (data.success) {
        state.userStudyMaterials = data.materials || [];
        if (state.selectedMaterialId === materialId) {
          state.selectedMaterialId = null;
          state.uploadedFiles = [];
          hide($('#uploaded-files'));
          $('#step1-next').disabled = true;
        }
        renderUserProcessedMaterials(state.userStudyMaterials);
        showToast('Document removed successfully');
      }
    } catch (err) {
      showToast(err.message || 'Failed to remove document', 'error');
    }
  }

  window.selectStudyMaterial = selectStudyMaterial;
  window.deleteStudyMaterial = deleteStudyMaterial;

  function updateUnitDropdown() {
    const datalist = $('#detected-units-list');
    if (!datalist) return;
    datalist.innerHTML = '';
    (state.detectedUnits || []).forEach(u => {
      const label = typeof u === 'string' ? u : (u.unit || u.label || '');
      if (label) {
        const opt = document.createElement('option');
        opt.value = label;
        datalist.appendChild(opt);
      }
    });
  }

  // ── Configuration (PDF mode) ───────────────────────────────
  function initConfig() {
    $('#q-type-chips').addEventListener('click', (e) => { const c = e.target.closest('.chip'); if (c) { c.classList.toggle('chip--active'); syncChipValues('q-type-chips', 'questionTypes'); updateLivePreview(); } });
    $('#bloom-chips').addEventListener('click', (e) => { const c = e.target.closest('.chip'); if (c) { c.classList.toggle('chip--active'); syncChipValues('bloom-chips', 'blooms'); } });
    $('#difficulty-control').addEventListener('click', (e) => { const b = e.target.closest('.segmented-control__btn'); if (b) { $$('#difficulty-control .segmented-control__btn').forEach(x => x.classList.remove('segmented-control__btn--active')); b.classList.add('segmented-control__btn--active'); state.config.difficulty = b.dataset.value; updateLivePreview(); } });

    $('#count-minus').addEventListener('click', () => { const i = $('#cfg-count'); i.value = Math.max(1, parseInt(i.value || 10) - 1); state.config.count = parseInt(i.value); updateLivePreview(); });
    $('#count-plus').addEventListener('click', () => { const i = $('#cfg-count'); i.value = Math.max(1, parseInt(i.value || 10) + 1); state.config.count = parseInt(i.value); updateLivePreview(); });
    $('#cfg-count').addEventListener('input', () => { state.config.count = Math.max(1, parseInt($('#cfg-count').value) || 1); updateLivePreview(); });
    $('#cfg-count').addEventListener('change', () => { state.config.count = Math.max(1, parseInt($('#cfg-count').value) || 1); updateLivePreview(); });

    ['cfg-subject', 'cfg-unit', 'cfg-topic', 'cfg-marks', 'cfg-duration'].forEach(id => {
      const el = $(`#${id}`);
      if (el) { el.addEventListener('input', updateLivePreview); el.addEventListener('change', updateLivePreview); }
    });

    // Knowledge Studio Live Preview Listeners & Steppers
    initKbLivePreview();
  }

  function syncChipValues(groupId, configKey) {
    state.config[configKey] = Array.from($$(`#${groupId} .chip--active`)).map(c => c.dataset.value);
  }

  function readConfig() {
    state.config.subject = $('#cfg-subject').value.trim();
    state.config.unit = $('#cfg-unit').value.trim();
    state.config.topic = $('#cfg-topic').value.trim();
    state.config.count = Math.max(1, parseInt($('#cfg-count').value) || 10);
    state.config.marks = $('#cfg-marks').value.trim() || '100';
    state.config.duration = $('#cfg-duration').value;
    state.config.instructions = $('#cfg-instructions').value.trim();
    syncChipValues('q-type-chips', 'questionTypes');
    syncChipValues('bloom-chips', 'blooms');
  }

  function updateLivePreview() {
    readConfig();
    $('#pv-subject').textContent = state.config.subject || '—';
    $('#pv-unit').textContent = state.config.unit || '(All Chapters)';
    $('#pv-count').textContent = state.config.count;
    $('#pv-difficulty').textContent = state.config.difficulty;
    $('#pv-duration').textContent = state.config.duration;
    $('#pv-marks').textContent = state.config.marks;

    const shortNames = { 'Multiple Choice Questions (MCQ)': 'MCQ', 'Short Answer Questions': 'Short Ans', 'Long Answer Questions': 'Long Ans', 'True/False': 'T/F', 'Fill in the Blanks': 'Fill Blanks' };
    $('#pv-types').innerHTML = state.config.questionTypes.map(t => `<span class="preview-paper__type-tag">${shortNames[t] || t}</span>`).join('');
  }

  // ── Curriculum Studio Live Preview ─────────────────────────
  function updateKbLivePreview() {
    const isCoursework = state.studioTab === 'coursework';
    if (isCoursework) {
      $('#kb-pv-header').textContent = 'EXAMINATION PAPER';
      $('#kb-pv-mode').textContent = 'Coursework Assessment';
      $('#kb-pv-topic').textContent = $('#kb-topic').value.trim() || '—';
      $('#kb-pv-scope-key').textContent = 'Audience:';
      $('#kb-pv-scope-val').textContent = $('#kb-audience').value;
      $('#kb-pv-count').textContent = $('#kb-count').value || '15';
      $('#kb-pv-difficulty').textContent = $('#kb-difficulty').value;
      $('#kb-pv-duration').textContent = $('#kb-time').value.trim() || '1 Hour';
      $('#kb-pv-marks').textContent = $('#kb-marks').value.trim() || '150';

      const shortNames = {
        'Multiple Choice Questions (MCQ)': 'MCQ',
        'Short Answer Questions': 'Short Ans',
        'Long Answer Questions': 'Long Ans',
        'True/False': 'T/F',
        'Fill in the Blanks': 'Fill Blanks'
      };
      const activeTypes = Array.from($$('#kb-type-chips .chip--active')).map(c => c.dataset.value);
      $('#kb-pv-types').innerHTML = activeTypes.map(t => `<span class="preview-paper__type-tag">${shortNames[t] || t}</span>`).join('');

      let badgesHtml = '';
      if ($('#kb-inc-answers')?.checked) badgesHtml += `<span class="badge" style="font-size:0.72rem; padding:3px 8px; border-radius:12px; background:var(--primary-light); color:var(--primary); font-weight:600;">Answers ✓</span>`;
      if ($('#kb-inc-explanations')?.checked) badgesHtml += `<span class="badge" style="font-size:0.72rem; padding:3px 8px; border-radius:12px; background:var(--primary-light); color:var(--primary); font-weight:600;">Explanations ✓</span>`;
      if ($('#kb-inc-hints')?.checked) badgesHtml += `<span class="badge" style="font-size:0.72rem; padding:3px 8px; border-radius:12px; background:var(--primary-light); color:var(--primary); font-weight:600;">Hints ✓</span>`;
      $('#kb-pv-badges').innerHTML = badgesHtml;
    } else {
      $('#kb-pv-header').textContent = 'TECHNICAL CODING PAPER';
      $('#kb-pv-mode').textContent = 'Algorithmic Studio';
      $('#kb-pv-topic').textContent = $('#dsa-topic').value.trim() || '—';
      $('#kb-pv-scope-key').textContent = 'Language:';
      $('#kb-pv-scope-val').textContent = $('#dsa-language').value;
      const count = parseInt($('#dsa-count').value) || 3;
      $('#kb-pv-count').textContent = count;
      $('#kb-pv-difficulty').textContent = $('#dsa-difficulty').value;
      $('#kb-pv-duration').textContent = '1 Hour';
      $('#kb-pv-marks').textContent = (count * 10).toString();

      $('#kb-pv-types').innerHTML = `<span class="preview-paper__type-tag">${$('#dsa-style').value.replace('-style Problem', '')}</span>`;

      let badgesHtml = '';
      if ($('#dsa-inc-constraints')?.checked) badgesHtml += `<span class="badge" style="font-size:0.72rem; padding:3px 8px; border-radius:12px; background:var(--primary-light); color:var(--primary); font-weight:600;">Constraints ✓</span>`;
      if ($('#dsa-inc-hints')?.checked) badgesHtml += `<span class="badge" style="font-size:0.72rem; padding:3px 8px; border-radius:12px; background:var(--primary-light); color:var(--primary); font-weight:600;">Hints ✓</span>`;
      if ($('#dsa-inc-solution')?.checked) badgesHtml += `<span class="badge" style="font-size:0.72rem; padding:3px 8px; border-radius:12px; background:var(--primary-light); color:var(--primary); font-weight:600;">Solution ✓</span>`;
      if ($('#dsa-inc-complexity')?.checked) badgesHtml += `<span class="badge" style="font-size:0.72rem; padding:3px 8px; border-radius:12px; background:var(--primary-light); color:var(--primary); font-weight:600;">Complexity ✓</span>`;
      $('#kb-pv-badges').innerHTML = badgesHtml;
    }
  }

  function initKbLivePreview() {
    // Coursework question count stepper
    $('#kb-count-minus')?.addEventListener('click', () => {
      const i = $('#kb-count');
      i.value = Math.max(1, parseInt(i.value || 15) - 1);
      updateKbLivePreview();
    });
    $('#kb-count-plus')?.addEventListener('click', () => {
      const i = $('#kb-count');
      i.value = Math.max(1, parseInt(i.value || 15) + 1);
      updateKbLivePreview();
    });
    $('#kb-count')?.addEventListener('input', updateKbLivePreview);
    $('#kb-count')?.addEventListener('change', updateKbLivePreview);

    // DSA question count stepper
    $('#dsa-count-minus')?.addEventListener('click', () => {
      const i = $('#dsa-count');
      i.value = Math.max(1, parseInt(i.value || 3) - 1);
      updateKbLivePreview();
    });
    $('#dsa-count-plus')?.addEventListener('click', () => {
      const i = $('#dsa-count');
      i.value = Math.max(1, parseInt(i.value || 3) + 1);
      updateKbLivePreview();
    });
    $('#dsa-count')?.addEventListener('input', updateKbLivePreview);
    $('#dsa-count')?.addEventListener('change', updateKbLivePreview);

    // Knowledge mode chip toggles
    $('#kb-type-chips')?.addEventListener('click', (e) => {
      const c = e.target.closest('.chip');
      if (c) {
        c.classList.toggle('chip--active');
        updateKbLivePreview();
      }
    });

    // Inputs in Coursework panel
    ['kb-topic', 'kb-audience', 'kb-difficulty', 'kb-time', 'kb-marks'].forEach(id => {
      const el = $(`#${id}`);
      if (el) { el.addEventListener('input', updateKbLivePreview); el.addEventListener('change', updateKbLivePreview); }
    });
    ['kb-inc-answers', 'kb-inc-explanations', 'kb-inc-hints'].forEach(id => {
      $(`#${id}`)?.addEventListener('change', updateKbLivePreview);
    });

    // Inputs in Algorithmic panel
    ['dsa-topic', 'dsa-language', 'dsa-style', 'dsa-difficulty'].forEach(id => {
      const el = $(`#${id}`);
      if (el) { el.addEventListener('input', updateKbLivePreview); el.addEventListener('change', updateKbLivePreview); }
    });
    ['dsa-inc-constraints', 'dsa-inc-hints', 'dsa-inc-solution', 'dsa-inc-complexity'].forEach(id => {
      $(`#${id}`)?.addEventListener('change', updateKbLivePreview);
    });

    updateKbLivePreview();
  }

  // ── Generation — PDF/RAG Mode ──────────────────────────────
  async function generatePdfQuestions(isRegen = false) {
    showGeneratingScreen(isRegen ? 'Regenerating questions from document…' : 'Generating questions from document…');

    try {
      const payload = {
        unit: state.config.unit || '',
        topic: state.config.topic || state.config.subject || 'Comprehensive Curriculum Concepts',
        question_types: state.config.questionTypes?.length ? state.config.questionTypes : ['Multiple Choice Questions (MCQ)'],
        difficulty: state.config.difficulty || 'Medium',
        count: state.config.count || 5,
        include_answers: true, include_explanations: true, include_sources: true,
        language: 'English',
        instructions: state.config.instructions || '',
        time_allowed: state.config.duration || '1 Hour',
        max_marks: state.config.marks || '100',
        username: state.user?.username || ''
      };

      const data = await api('/api/generate-pdf-questions', { method: 'POST', body: JSON.stringify(payload) });
      handleGenerationResult(data.questions, state.config.subject, data.document, data.all_documents);
    } catch (err) {
      showToast('Generation failed: ' + err.message, 'error');
      setTimeout(() => {
        if (state.generatedQuestions && state.generatedQuestions.length) {
          if (state._goToStep) state._goToStep(4);
        } else {
          if (state._goToStep) state._goToStep(2);
        }
      }, 1500);
    }
  }

  // ── Generation — Knowledge Mode ────────────────────────────
  async function generateKnowledgeQuestions(isRegen = false) {
    const topic = $('#kb-topic')?.value.trim() || state.config.subject;
    if (!topic) { showToast('Please enter a topic', 'error'); return; }

    const kbTypes = Array.from($$('#kb-type-chips .chip--active')).map(c => c.dataset.value);
    const activeTypes = kbTypes.length ? kbTypes : (state.config.questionTypes?.length ? state.config.questionTypes : ['Multiple Choice Questions (MCQ)']);

    // Switch to step 3 (generating screen)
    state.genMode = 'knowledge';
    state.studioTab = 'coursework';
    showGeneratingScreen(isRegen ? 'Regenerating questions from curriculum…' : 'Generating curriculum questions…');

    try {
      const payload = {
        topic: topic,
        target_audience: $('#kb-audience')?.value || 'Engineering Undergraduates',
        question_types: activeTypes,
        difficulty: $('#kb-difficulty')?.value || state.config.difficulty || 'Medium',
        count: parseInt($('#kb-count')?.value) || state.config.count || (state.generatedQuestions?.length || 10),
        include_answers: $('#kb-inc-answers') ? $('#kb-inc-answers').checked : true,
        include_explanations: $('#kb-inc-explanations') ? $('#kb-inc-explanations').checked : true,
        include_hints: $('#kb-inc-hints') ? $('#kb-inc-hints').checked : false,
        instructions: $('#kb-notes')?.value.trim() || state.config.instructions || '',
        time_allowed: $('#kb-time')?.value.trim() || state.config.duration || '1 Hour',
        max_marks: $('#kb-marks')?.value.trim() || state.config.marks || '150',
        username: state.user?.username || ''
      };

      const data = await api('/api/generate-knowledge-questions', { method: 'POST', body: JSON.stringify(payload) });

      // Update config for preview
      state.config.subject = topic;
      state.config.duration = payload.time_allowed;
      state.config.marks = payload.max_marks;
      state.config.difficulty = payload.difficulty;
      state.config.count = payload.count;
      state.config.questionTypes = activeTypes;

      handleGenerationResult(data.questions, topic, data.document, data.all_documents);
    } catch (err) {
      showToast('Generation failed: ' + err.message, 'error');
      setTimeout(() => {
        if (state.generatedQuestions && state.generatedQuestions.length) {
          $$('.step-content').forEach(sc => sc.classList.remove('step-content--active'));
          $('#step-4').classList.add('step-content--active');
          $$('.gen-mode-content').forEach(c => c.classList.remove('gen-mode-content--active'));
          $('#mode-pdf').classList.add('gen-mode-content--active');
        } else {
          $$('.step-content').forEach(sc => sc.classList.remove('step-content--active'));
          $$('.gen-mode-content').forEach(c => c.classList.remove('gen-mode-content--active'));
          $('#mode-knowledge').classList.add('gen-mode-content--active');
        }
      }, 1500);
    }
  }

  function initKnowledgeGeneration() {
    $('#kb-generate-btn')?.addEventListener('click', () => generateKnowledgeQuestions(false));
  }

  // ── Generation — DSA Mode ──────────────────────────────────
  async function generateDSAQuestions(isRegen = false) {
    const topic = $('#dsa-topic')?.value.trim() || state.config.subject?.replace(/^DSA:\s*/, '').replace(/\s*\([^)]*\)$/, '') || 'Data Structures & Algorithms';
    if (!topic) { showToast('Please enter a DSA topic', 'error'); return; }

    state.genMode = 'knowledge';
    state.studioTab = 'algorithmic';
    showGeneratingScreen(isRegen ? 'Regenerating algorithmic problems…' : 'Generating algorithmic problems…');

    try {
      const payload = {
        topic: topic,
        language: $('#dsa-language')?.value || 'Python',
        problem_style: $('#dsa-style')?.value || 'Coding Challenge with Test Cases',
        difficulty: $('#dsa-difficulty')?.value || state.config.difficulty || 'Medium',
        count: parseInt($('#dsa-count')?.value) || state.config.count || (state.generatedQuestions?.length || 3),
        include_constraints: $('#dsa-inc-constraints') ? $('#dsa-inc-constraints').checked : true,
        include_hints: $('#dsa-inc-hints') ? $('#dsa-inc-hints').checked : true,
        include_solution: $('#dsa-inc-solution') ? $('#dsa-inc-solution').checked : true,
        include_complexity: $('#dsa-inc-complexity') ? $('#dsa-inc-complexity').checked : true,
        instructions: $('#dsa-notes')?.value.trim() || state.config.instructions || '',
        username: state.user?.username || ''
      };

      const data = await api('/api/generate-dsa-questions', { method: 'POST', body: JSON.stringify(payload) });

      state.config.subject = `DSA: ${topic} (${payload.language})`;
      state.config.duration = '1 Hour';
      state.config.marks = '150';
      state.config.difficulty = payload.difficulty;
      state.config.count = payload.count;

      handleGenerationResult(data.questions, state.config.subject, data.document, data.all_documents);
    } catch (err) {
      showToast('Generation failed: ' + err.message, 'error');
      setTimeout(() => {
        if (state.generatedQuestions && state.generatedQuestions.length) {
          $$('.step-content').forEach(sc => sc.classList.remove('step-content--active'));
          $('#step-4').classList.add('step-content--active');
          $$('.gen-mode-content').forEach(c => c.classList.remove('gen-mode-content--active'));
          $('#mode-pdf').classList.add('gen-mode-content--active');
        } else {
          $$('.step-content').forEach(sc => sc.classList.remove('step-content--active'));
          $$('.gen-mode-content').forEach(c => c.classList.remove('gen-mode-content--active'));
          $('#mode-knowledge').classList.add('gen-mode-content--active');
        }
      }, 1500);
    }
  }

  function initDSAGeneration() {
    $('#dsa-generate-btn')?.addEventListener('click', () => generateDSAQuestions(false));
  }

  // ── Shared generation helpers ──────────────────────────────
  function showGeneratingScreen(title) {
    // Make the step-3 generating screen visible, hiding other content
    $$('.gen-mode-content').forEach(c => c.classList.remove('gen-mode-content--active'));
    $('#mode-pdf').classList.add('gen-mode-content--active');

    $$('.step-content').forEach(sc => sc.classList.remove('step-content--active'));
    $('#step-3').classList.add('step-content--active');

    // Hide stepper for knowledge mode
    const stepper = $('#stepper');
    if (stepper) stepper.style.display = state.genMode === 'knowledge' ? 'none' : '';

    $('#gen-title').textContent = title || 'Generating your question paper…';
    animateGenerationStages();
  }

  function animateGenerationStages() {
    const stages = $$('#gen-stages .gen-stage');
    const isKnowledge = state.genMode === 'knowledge';
    const texts = isKnowledge ? [
      'Analyzing curriculum topic',
      'Structuring core concepts',
      'Setting cognitive levels',
      "Applying Bloom's Taxonomy",
      'Generating questions',
      'Creating final paper'
    ] : [
      'Reading document',
      'Extracting important concepts',
      'Retrieving relevant content',
      "Applying Bloom's Taxonomy",
      'Generating questions',
      'Creating final paper'
    ];

    stages.forEach((s, i) => {
      const span = s.querySelector('span:not(.spinner)');
      if (span && texts[i]) span.textContent = texts[i];
      s.classList.remove('gen-stage--done', 'gen-stage--active');
      if (i < 3) { s.classList.add('gen-stage--done'); s.querySelector('.gen-stage__icon').innerHTML = '✓'; }
      else { s.querySelector('.gen-stage__icon').innerHTML = '○'; }
    });
    if (stages[3]) {
      stages[3].classList.add('gen-stage--active');
      stages[3].querySelector('.gen-stage__icon').innerHTML = '<span class="spinner spinner--xs"></span>';
    }

    for (let i = 4; i < stages.length; i++) {
      setTimeout(() => {
        if (!stages[i] || !stages[i - 1]) return;
        stages[i - 1].classList.remove('gen-stage--active');
        stages[i - 1].classList.add('gen-stage--done');
        stages[i - 1].querySelector('.gen-stage__icon').innerHTML = '✓';
        stages[i].classList.add('gen-stage--active');
        stages[i].querySelector('.gen-stage__icon').innerHTML = '<span class="spinner spinner--xs"></span>';
      }, (i - 3) * 2000);
    }
  }

  function handleGenerationResult(questions, subject, docRecord, allDocuments) {
    if (!questions || !questions.length) {
      showToast('No questions were generated. Please try again.', 'error');
      setTimeout(() => {
        if (state.generatedQuestions && state.generatedQuestions.length) {
          if (state.genMode === 'pdf' && state._goToStep) {
            state._goToStep(4);
          } else {
            $$('.step-content').forEach(sc => sc.classList.remove('step-content--active'));
            $('#step-4').classList.add('step-content--active');
          }
        } else {
          if (state.genMode === 'pdf' && state._goToStep) {
            state._goToStep(2);
          } else {
            $$('.step-content').forEach(sc => sc.classList.remove('step-content--active'));
            $$('.gen-mode-content').forEach(c => c.classList.remove('gen-mode-content--active'));
            $('#mode-knowledge').classList.add('gen-mode-content--active');
          }
        }
      }, 1500);
      return;
    }

    // Mark all stages done
    $$('#gen-stages .gen-stage').forEach(s => {
      s.classList.remove('gen-stage--active');
      s.classList.add('gen-stage--done');
      s.querySelector('.gen-stage__icon').innerHTML = '✓';
    });

    state.generatedQuestions = questions;

    // Synchronize documents list
    if (Array.isArray(allDocuments)) {
      state.generatedDocuments = allDocuments;
    } else if (docRecord) {
      if (!state.generatedDocuments.find(d => d.id === docRecord.id)) {
        state.generatedDocuments.unshift(docRecord);
      }
    } else {
      state.generatedDocuments.unshift({
        id: 'doc_' + Date.now(),
        subject: subject || 'Untitled',
        difficulty: state.config.difficulty,
        duration: state.config.duration,
        marks: state.config.marks,
        created_at: new Date().toISOString(),
        questions: questions
      });
    }

    setTimeout(() => {
      // Show review step
      $$('.step-content').forEach(sc => sc.classList.remove('step-content--active'));
      $('#step-4').classList.add('step-content--active');

      const stepper = $('#stepper');
      if (state.genMode === 'pdf') {
        stepper.style.display = '';
        state._goToStep(4);
      } else {
        stepper.style.display = 'none';
      }

      renderPaperPreview();
      updateStats();
      renderRecentPapers();
    }, 800);
  }

  // ── Paper Preview ──────────────────────────────────────────
  function renderPaperPreview() {
    const questions = state.generatedQuestions;
    if (!questions.length) return;

    $('#doc-subject').textContent = state.config.subject || 'General';
    $('#doc-duration').textContent = state.config.duration;
    $('#doc-marks').textContent = state.config.marks;
    $('#doc-date').textContent = formatDate();

    // Group by type
    const groups = {};
    questions.forEach((q, i) => {
      const type = q.question_type || q.type || 'General';
      if (!groups[type]) groups[type] = [];
      groups[type].push({ ...q, _index: i });
    });

    const partLabels = ['A', 'B', 'C', 'D', 'E', 'F'];
    let partIdx = 0, globalNum = 1;

    const html = Object.entries(groups).map(([type, qs]) => {
      const part = partLabels[partIdx++] || '';
      const qHtml = qs.map(q => {
        const num = globalNum++;
        const text = q.question || q.text || '';
        const marks = q.marks || q.mark || '—';
        const diff = q.difficulty || '';

        let optionsHtml = '';
        if (q.options?.length) {
          const labels = ['A', 'B', 'C', 'D', 'E', 'F'];
          optionsHtml = `<div class="paper-question__options">${q.options.map((opt, oi) => {
            const t = typeof opt === 'string' ? opt : (opt.text || opt.option || '');
            return `<div class="paper-question__option"><span class="paper-question__option-label">${labels[oi]})</span><span>${t}</span></div>`;
          }).join('')}</div>`;
        }

        return `<div class="paper-question" data-index="${q._index}">
          <div class="paper-question__header">
            <div class="paper-question__text"><span class="paper-question__number">${num}.</span> ${text}</div>
            <span class="paper-question__marks">${marks} marks</span>
          </div>
          ${optionsHtml}
          <div class="paper-question__meta">
            ${diff ? `<span class="paper-question__tag paper-question__tag--difficulty-${diff}">${diff}</span>` : ''}
            ${q.bloom_level ? `<span class="paper-question__tag">${q.bloom_level}</span>` : ''}
            ${q.blooms_level ? `<span class="paper-question__tag">${q.blooms_level}</span>` : ''}
          </div>
          <div class="paper-question__actions">
            <button class="paper-question__action-btn" title="Edit" data-action="edit" data-index="${q._index}">
              <svg viewBox="0 0 20 20" fill="none"><path d="M13.5 3.5l3 3L6 17H3v-3L13.5 3.5z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg>
            </button>
            <button class="paper-question__action-btn" title="Regenerate" data-action="regen" data-index="${q._index}">
              <svg viewBox="0 0 20 20" fill="none"><path d="M17 10A7 7 0 113 10M3 10A7 7 0 1117 10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
            </button>
          </div>
        </div>`;
      }).join('');

      return `<div class="paper-section"><div class="paper-section__title">Part ${part} — ${type}</div>${qHtml}</div>`;
    }).join('');

    $('#paper-body').innerHTML = html;

    $$('.paper-question__action-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const idx = parseInt(btn.dataset.index);
        if (btn.dataset.action === 'edit') openEditModal(idx);
        if (btn.dataset.action === 'regen') regenerateQuestion(idx);
      });
    });
  }

  // ── Edit Modal ─────────────────────────────────────────────
  function initEditModal() {
    $('#edit-modal-close').addEventListener('click', closeEditModal);
    $('#edit-cancel-btn').addEventListener('click', closeEditModal);
    $('#edit-modal').addEventListener('click', (e) => { if (e.target === $('#edit-modal')) closeEditModal(); });

    $('#edit-save-btn').addEventListener('click', () => {
      const q = state.generatedQuestions[state.editingIndex];
      if (!q) return;
      q.question = $('#edit-q-text').value;
      q.answer = $('#edit-q-answer').value;
      q.marks = parseInt($('#edit-q-marks').value) || q.marks;
      q.difficulty = $('#edit-q-difficulty').value;
      const optInputs = $$('#edit-options-list input');
      if (optInputs.length && q.options) q.options = Array.from(optInputs).map(inp => inp.value);
      closeEditModal();
      renderPaperPreview();
      showToast('Question updated');
    });
  }

  function openEditModal(index) {
    state.editingIndex = index;
    const q = state.generatedQuestions[index];
    if (!q) return;
    $('#edit-q-text').value = q.question || q.text || '';
    $('#edit-q-answer').value = q.answer || q.correct_answer || '';
    $('#edit-q-marks').value = q.marks || q.mark || '';
    $('#edit-q-difficulty').value = q.difficulty || 'Medium';

    const optGroup = $('#edit-options-group'), optList = $('#edit-options-list');
    if (q.options?.length) {
      show(optGroup);
      const labels = ['A', 'B', 'C', 'D', 'E', 'F'];
      optList.innerHTML = q.options.map((opt, i) => {
        const t = typeof opt === 'string' ? opt : (opt.text || opt.option || '');
        return `<div class="form-group" style="margin-bottom:8px"><div class="input-wrap" style="position:relative"><span style="position:absolute;left:14px;top:50%;transform:translateY(-50%);font-weight:600;color:var(--text-muted);font-size:.85rem">${labels[i]})</span><input type="text" class="form-input" style="padding-left:38px" value="${t}" /></div></div>`;
      }).join('');
    } else { hide(optGroup); optList.innerHTML = ''; }
    show($('#edit-modal'));
  }

  function closeEditModal() { hide($('#edit-modal')); state.editingIndex = -1; }

  async function regenerateQuestion(index) {
    try {
      showToast('Regenerating question…');
      const targetQ = state.generatedQuestions[index];
      const data = await api('/api/regenerate-question', {
        method: 'POST',
        body: JSON.stringify({
          question_index: index,
          question: targetQ,
          username: state.user?.username || ''
        })
      });
      if (data.question) {
        state.generatedQuestions[index] = data.question;
        renderPaperPreview();
        showToast('Question regenerated');
      }
    } catch (err) { showToast('Regeneration failed: ' + err.message, 'error'); }
  }

  // ── Actions ────────────────────────────────────────────────
  function initActions() {
    $('#action-edit').addEventListener('click', () => { if (state.generatedQuestions.length) openEditModal(0); });
    $('#action-regenerate').addEventListener('click', async () => {
      if (state.genMode === 'pdf') {
        state._goToStep(3);
        await generatePdfQuestions(true);
      } else if (state.genMode === 'knowledge' && state.studioTab === 'algorithmic') {
        await generateDSAQuestions(true);
      } else if (state.genMode === 'knowledge') {
        await generateKnowledgeQuestions(true);
      } else {
        if (state.uploadedFiles?.length > 0 || state.selectedMaterialId) {
          state.genMode = 'pdf';
          state._goToStep(3);
          await generatePdfQuestions(true);
        } else {
          state.genMode = 'knowledge';
          await generateKnowledgeQuestions(true);
        }
      }
    });

    $('#action-save').addEventListener('click', async () => {
      try { await api('/api/save-paper', { method: 'POST', body: JSON.stringify({ questions: state.generatedQuestions }) }); showToast('Paper saved'); }
      catch (err) { showToast('Save failed: ' + err.message, 'error'); }
    });

    $('#action-download-pdf').addEventListener('click', async () => {
      try {
        const exportPayload = {
          questions: state.generatedQuestions,
          subject: state.config.subject || 'Examination Paper',
          department: '',
          max_marks: state.config.marks || '100',
          time_allowed: state.config.duration || '1 Hour',
          blooms_level: ''
        };
        const res = await fetch('/api/export-pdf', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(exportPayload) });
        if (!res.ok) throw new Error('Export failed');
        downloadBlob(await res.blob(), `SmartQGen_${state.config.subject || 'Paper'}.pdf`);
        showToast('PDF downloaded');
      } catch (err) { showToast('PDF export failed: ' + err.message, 'error'); }
    });

    $('#action-download-docx').addEventListener('click', async () => {
      try {
        const res = await fetch('/api/export-csv', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ questions: state.generatedQuestions }) });
        if (!res.ok) throw new Error('Export failed');
        downloadBlob(await res.blob(), `SmartQGen_${state.config.subject || 'Paper'}.csv`);
        showToast('CSV downloaded');
      } catch (err) { showToast('CSV export failed: ' + err.message, 'error'); }
    });

    $('#action-print').addEventListener('click', () => window.print());
  }

  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  // ── History ────────────────────────────────────────────────
  function renderHistory() {
    const grid = $('#history-grid');
    const docs = state.generatedDocuments.slice().reverse();

    if (!docs.length) {
      grid.innerHTML = '';
      const empty = $('#history-empty');
      if (empty) { grid.appendChild(empty.cloneNode(true)).hidden = false; }
      return;
    }

    grid.innerHTML = docs.map((doc, i) => {
      const subject = doc.subject || 'Untitled';
      const qCount = doc.questions?.length || 0;
      const date = formatDate(doc.created_at || doc.generated_at);
      const diff = doc.difficulty || '';
      const duration = doc.duration || doc.time_allowed || '';
      let diffClass = '';
      if (diff === 'Easy') diffClass = 'qb-tag--success';
      else if (diff === 'Medium') diffClass = 'qb-tag--warning';
      else if (diff === 'Hard') diffClass = 'qb-tag--danger';

      return `<div class="history-card">
        <div class="history-card__subject">${subject}</div>
        <div class="history-card__meta"><svg viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.2"/><path d="M8 4v4l2 2" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg> ${date}</div>
        <div class="history-card__meta"><svg viewBox="0 0 16 16" fill="none"><rect x="2" y="2" width="12" height="12" rx="2" stroke="currentColor" stroke-width="1.2"/><path d="M5 5h6M5 8h4" stroke="currentColor" stroke-width="1" stroke-linecap="round"/></svg> ${qCount} questions${duration ? ' • ' + duration : ''}</div>
        <div class="history-card__tags">${diff ? `<span class="qb-tag ${diffClass}">${diff}</span>` : ''}</div>
        <div class="history-card__actions">
          <button class="btn btn--outline btn--sm" onclick="SmartQGen.viewHistoryPaper(${i})">View</button>
          <button class="btn btn--primary btn--sm" onclick="SmartQGen.downloadHistoryPaper(${i})">Download</button>
          <button class="btn btn--ghost btn--sm" style="color:var(--color-danger, #ef4444);" onclick="SmartQGen.deleteHistoryPaper('${doc._id || doc.id}')">Delete</button>
        </div>
      </div>`;
    }).join('');
  }

  // ── Public API ─────────────────────────────────────────────
  window.SmartQGen = {
    viewPaper(id) {
      const doc = state.generatedDocuments.find(d => (d._id || d.id) === id);
      if (doc?.questions) {
        state.generatedQuestions = doc.questions;
        state.config.subject = doc.subject || '';
        state.config.duration = doc.duration || doc.time_allowed || '1 Hour';
        state.config.marks = doc.marks || doc.max_marks || '100';
        state.config.difficulty = doc.difficulty || 'Medium';
        state.config.count = doc.questions.length;
        if (doc.source_file === 'AI Curriculum Knowledge') {
          state.genMode = 'knowledge';
          state.studioTab = 'coursework';
        } else if (doc.source_file === 'Algorithmic Problem Studio') {
          state.genMode = 'knowledge';
          state.studioTab = 'algorithmic';
        } else if (doc.source_file) {
          state.genMode = 'pdf';
        }
        navigateTo('generate');
        // Show review
        $$('.gen-mode-content').forEach(c => c.classList.remove('gen-mode-content--active'));
        $('#mode-pdf').classList.add('gen-mode-content--active');
        $('#stepper').style.display = 'none';
        $$('.step-content').forEach(sc => sc.classList.remove('step-content--active'));
        $('#step-4').classList.add('step-content--active');
        renderPaperPreview();
      }
    },
    viewHistoryPaper(reverseIndex) {
      const docs = state.generatedDocuments.slice().reverse();
      const doc = docs[reverseIndex];
      if (doc?.questions) {
        state.generatedQuestions = doc.questions;
        state.config.subject = doc.subject || '';
        state.config.duration = doc.duration || doc.time_allowed || '1 Hour';
        state.config.marks = doc.marks || doc.max_marks || '100';
        state.config.difficulty = doc.difficulty || 'Medium';
        state.config.count = doc.questions.length;
        if (doc.source_file === 'AI Curriculum Knowledge') {
          state.genMode = 'knowledge';
          state.studioTab = 'coursework';
        } else if (doc.source_file === 'Algorithmic Problem Studio') {
          state.genMode = 'knowledge';
          state.studioTab = 'algorithmic';
        } else if (doc.source_file) {
          state.genMode = 'pdf';
        }
        navigateTo('generate');
        $$('.gen-mode-content').forEach(c => c.classList.remove('gen-mode-content--active'));
        $('#mode-pdf').classList.add('gen-mode-content--active');
        $('#stepper').style.display = 'none';
        $$('.step-content').forEach(sc => sc.classList.remove('step-content--active'));
        $('#step-4').classList.add('step-content--active');
        renderPaperPreview();
      }
    },
    async downloadHistoryPaper(reverseIndex) {
      const docs = state.generatedDocuments.slice().reverse();
      const doc = docs[reverseIndex];
      if (!doc) return;
      try {
        const exportPayload = {
          questions: doc.questions,
          subject: doc.subject || 'Examination Paper',
          department: doc.department || '',
          max_marks: doc.max_marks || doc.marks || '150',
          time_allowed: doc.time_allowed || doc.duration || '1 Hour',
          blooms_level: doc.blooms_level || ''
        };
        const res = await fetch('/api/export-pdf', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(exportPayload) });
        if (!res.ok) throw new Error('Export failed');
        downloadBlob(await res.blob(), `SmartQGen_${doc.subject || 'Paper'}.pdf`);
      } catch (err) { showToast('Download failed: ' + err.message, 'error'); }
    },
    async deleteHistoryPaper(id) {
      if (!confirm('Are you sure you want to delete this question paper?')) return;
      try {
        const userParam = state.user?.username ? `?username=${encodeURIComponent(state.user.username)}` : '';
        const data = await api(`/api/document/${encodeURIComponent(id)}${userParam}`, { method: 'DELETE' });
        if (data.success && Array.isArray(data.documents)) {
          state.generatedDocuments = data.documents;
        } else {
          state.generatedDocuments = state.generatedDocuments.filter(d => (d._id || d.id) !== id);
        }
        updateStats();
        renderHistory();
        renderRecentPapers();
        showToast('Question paper deleted', 'success');
      } catch (err) {
        showToast('Delete failed: ' + err.message, 'error');
      }
    }
  };

  // ── Admin Dashboard ─────────────────────────────────────────
  let adminUsersList = [];

  async function initAdminDashboard() {
    if (!state.user || (state.user.role || '').toLowerCase() !== 'admin') {
      showToast('Admin privileges required.', 'error');
      navigateTo('dashboard');
      return;
    }
    await loadAdminUsers();
  }

  async function loadAdminUsers() {
    try {
      const data = await api('/api/admin/users');
      adminUsersList = data.users || [];
      renderAdminStats();
      renderAdminTable(adminUsersList);
    } catch (err) {
      showToast(err.message || 'Failed to load users list', 'error');
    }
  }

  function renderAdminStats() {
    const totalUsers = adminUsersList.length;
    const totalPapers = adminUsersList.reduce((acc, u) => acc + (u.papers_count || 0), 0);
    const totalQuestions = adminUsersList.reduce((acc, u) => acc + (u.questions_count || 0), 0);
    const totalAdmins = adminUsersList.filter(u => (u.role || '').toLowerCase() === 'admin').length;

    if ($('#admin-stat-users')) $('#admin-stat-users').textContent = totalUsers;
    if ($('#admin-stat-papers')) $('#admin-stat-papers').textContent = totalPapers;
    if ($('#admin-stat-questions')) $('#admin-stat-questions').textContent = totalQuestions;
    if ($('#admin-stat-admins')) $('#admin-stat-admins').textContent = totalAdmins;
  }

  function renderAdminTable(users) {
    const tbody = $('#admin-users-tbody');
    const emptyEl = $('#admin-users-empty');
    if (!tbody) return;

    if (!users || users.length === 0) {
      tbody.innerHTML = '';
      show(emptyEl);
      return;
    }
    hide(emptyEl);

    tbody.innerHTML = users.map(u => {
      const isCurrentAdmin = (u.username || '').toLowerCase() === (state.user?.username || '').toLowerCase();
      const isPrimaryAdmin = (u.username || '').toLowerCase() === 'admin';
      const isAdmin = (u.role || '').toLowerCase() === 'admin';
      const initials = (u.full_name || u.username || 'U').charAt(0).toUpperCase();

      return `
        <tr>
          <td>
            <div class="admin-user-cell">
              <div class="admin-user-avatar ${isAdmin ? 'admin-user-avatar--admin' : ''}">${initials}</div>
              <div>
                <div class="admin-user-name">${escapeHtml(u.full_name || u.username)}</div>
                <div class="admin-user-sub">@${escapeHtml(u.username)}${u.department ? ' • ' + escapeHtml(u.department) : ''}</div>
              </div>
            </div>
          </td>
          <td>
            <span class="role-badge role-badge--${isAdmin ? 'admin' : (u.role === 'faculty' ? 'faculty' : 'user')}">
              ${isAdmin ? '🛡️ Admin' : (u.role === 'faculty' ? '🎓 Faculty' : '👤 User')}
            </span>
          </td>
          <td><strong>${u.papers_count || 0}</strong> papers</td>
          <td>${u.questions_count || 0} questions</td>
          <td>${u.created_at ? formatDate(u.created_at) : 'Active'}</td>
          <td>
            <div class="admin-actions">
              <button class="btn btn--outline btn--xs" onclick="window.viewUserPapers('${escapeHtml(u.username)}')">
                View Papers
              </button>
              ${!isAdmin ? `
                <button class="btn btn--promote btn--xs" onclick="window.promoteUser('${escapeHtml(u.username)}')">
                  Promote to Admin
                </button>
              ` : `
                <button class="btn btn--promote btn--xs" disabled title="Already an administrator. Admins cannot be demoted.">
                  Admin
                </button>
              `}
              ${(!isCurrentAdmin && !isPrimaryAdmin) ? `
                <button class="btn btn--danger-subtle btn--xs" onclick="window.deleteUser('${escapeHtml(u.username)}')">
                  Delete
                </button>
              ` : `
                <button class="btn btn--danger-subtle btn--xs" disabled title="${isPrimaryAdmin ? 'Primary admin account cannot be deleted' : 'You cannot delete your own account'}">
                  Delete
                </button>
              `}
            </div>
          </td>
        </tr>
      `;
    }).join('');
  }

  function initAdmin() {
    $('#admin-refresh-btn')?.addEventListener('click', () => {
      loadAdminUsers();
      showToast('Admin data refreshed', 'success');
    });

    $('#admin-search-users')?.addEventListener('input', (e) => {
      const q = e.target.value.toLowerCase().trim();
      if (!q) {
        renderAdminTable(adminUsersList);
        return;
      }
      const filtered = adminUsersList.filter(u =>
        (u.username || '').toLowerCase().includes(q) ||
        (u.full_name || '').toLowerCase().includes(q) ||
        (u.department || '').toLowerCase().includes(q) ||
        (u.role || '').toLowerCase().includes(q)
      );
      renderAdminTable(filtered);
    });

    // Papers modal close
    $('#admin-papers-modal-close')?.addEventListener('click', () => hide($('#admin-papers-modal')));
    $('#admin-papers-modal-done')?.addEventListener('click', () => hide($('#admin-papers-modal')));
  }

  // Global window functions for table action buttons
  window.viewUserPapers = async function(username) {
    try {
      const data = await api(`/api/admin/user-papers/${encodeURIComponent(username)}`);
      const papers = data.documents || [];
      $('#admin-papers-modal-title').textContent = `Papers by @${username}`;
      $('#admin-papers-modal-sub').textContent = `${papers.length} question paper${papers.length === 1 ? '' : 's'} generated`;

      const listEl = $('#admin-user-papers-list');
      if (papers.length === 0) {
        listEl.innerHTML = `<div class="empty-state" style="padding: 24px;"><p class="empty-state__text">No papers generated yet</p><p class="empty-state__sub">User @${escapeHtml(username)} has not created any examination papers.</p></div>`;
      } else {
        listEl.innerHTML = papers.map(p => `
          <div class="admin-paper-item">
            <div class="admin-paper-info">
              <h4>${escapeHtml(p.subject || 'Examination Paper')}</h4>
              <div class="admin-paper-meta">
                <span>📝 ${p.questions?.length || p.count || 0} Questions</span>
                <span>📅 ${p.created_at || 'Recently'}</span>
                ${p.blooms_level ? `<span>🎯 ${escapeHtml(p.blooms_level)}</span>` : ''}
              </div>
            </div>
            <div>
              <a href="/api/download-document-pdf/${encodeURIComponent(p.id || p._id)}" target="_blank" class="btn btn--outline btn--xs">
                Download PDF
              </a>
            </div>
          </div>
        `).join('');
      }

      show($('#admin-papers-modal'));
    } catch (err) {
      showToast(err.message || 'Failed to fetch user papers', 'error');
    }
  };

  window.promoteUser = async function(username) {
    if (!confirm(`Are you sure you want to promote "${username}" to Administrator?\n\nIMPORTANT: Once promoted, administrators cannot be demoted.`)) {
      return;
    }
    try {
      const res = await api(`/api/admin/users/${encodeURIComponent(username)}/promote`, { method: 'POST' });
      showToast(res.message || `User @${username} is now an administrator!`, 'success');
      await loadAdminUsers();
    } catch (err) {
      showToast(err.message || 'Failed to promote user', 'error');
    }
  };

  window.deleteUser = async function(username) {
    if (!confirm(`Are you sure you want to permanently delete user "${username}" and all of their generated examination papers?\n\nThis action CANNOT be undone.`)) {
      return;
    }
    try {
      const res = await api(`/api/admin/users/${encodeURIComponent(username)}`, { method: 'DELETE' });
      showToast(res.message || `User @${username} deleted successfully`, 'success');
      await loadAdminUsers();
    } catch (err) {
      showToast(err.message || 'Failed to delete user', 'error');
    }
  };

  // ── Init ───────────────────────────────────────────────────
  function init() {
    initLogin();
    initAppShell();
    initModeSelector();
    initStudioTabs();
    initStepper();
    initUpload();
    initConfig();
    initEditModal();
    initActions();
    initKnowledgeGeneration();
    initDSAGeneration();
    initAdmin();
  }

  document.addEventListener('DOMContentLoaded', init);
})();
