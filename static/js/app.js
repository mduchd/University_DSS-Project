/**
 * LA BÀN ĐẠI HỌC - HỆ THỐNG HỖ TRỢ RA QUYẾT ĐỊNH TUYỂN SINH
 * JavaScript Application Logic
 * Icon System: Unified SVG Vector Icons (Lucide/Feather style, 24x24 viewBox, stroke-width=2)
 */

(function () {
  "use strict";

  const { combinations, subjectNames } = window.APP_CONFIG;

  // Unified SVG Icon Definitions
  const ICONS = {
    check: `<svg class="ui-icon ui-icon-sm" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>`,
    plus: `<svg class="ui-icon ui-icon-sm" viewBox="0 0 24 24"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>`,
    arrowUp: `<svg class="ui-icon ui-icon-sm" viewBox="0 0 24 24"><polyline points="18 15 12 9 6 15"/></svg>`,
    arrowDown: `<svg class="ui-icon ui-icon-sm" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg>`,
    close: `<svg class="ui-icon ui-icon-sm" viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`,
    school: `<svg class="ui-icon ui-icon-sm" viewBox="0 0 24 24"><path d="M22 10v6M2 10l10-5 10 5-10 5z"/><path d="M6 12v5c3 3 9 3 12 0v-5"/></svg>`,
    bookmark: `<svg class="ui-icon ui-icon-xl" viewBox="0 0 24 24"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>`,
    sectors: {
      code: `<svg class="ui-icon ui-icon-lg" viewBox="0 0 24 24"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>`,
      "trending-up": `<svg class="ui-icon ui-icon-lg" viewBox="0 0 24 24"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>`,
      "dollar-sign": `<svg class="ui-icon ui-icon-lg" viewBox="0 0 24 24"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>`,
      truck: `<svg class="ui-icon ui-icon-lg" viewBox="0 0 24 24"><rect x="1" y="3" width="15" height="13"/><polygon points="16 8 20 8 23 11 23 16 16 16 16 8"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/></svg>`,
      cpu: `<svg class="ui-icon ui-icon-lg" viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y1="9"/><line x1="20" y1="14" x2="23" y1="14"/><line x1="1" y1="9" x2="4" y1="9"/><line x1="1" y1="14" x2="4" y1="14"/></svg>`,
      activity: `<svg class="ui-icon ui-icon-lg" viewBox="0 0 24 24"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>`,
    },
  };

  // State Management
  const state = {
    activeView: "recommend",
    recommendations: null,
    activeBucket: "all",
    admissionsSearch: {
      q: "",
      combination: "",
      group: "",
      scale: "30",
      sort: "cutoff_desc",
      page: 1,
      limit: 15,
      total: 0,
      pages: 1,
      loading: false,
    },
    careerLoaded: false,
    wishlist: JSON.parse(localStorage.getItem("dss_user_wishlist") || "[]"),
    interests: loadStoredInterests(),
    auth: {
      token: localStorage.getItem("dss_auth_token"),
      user: null,
      mode: "login",
      googleEnabled: false,
      googleInitialized: false,
    },
  };

  // DOM Elements
  const elements = {
    // Nav
    navBtns: document.querySelectorAll(".nav-btn"),
    views: document.querySelectorAll(".app-view"),
    brandLink: document.querySelector(".brand"),
    authLoginBtn: document.getElementById("auth-login-btn"),
    authRegisterBtn: document.getElementById("auth-register-btn"),
    authAccountBtn: document.getElementById("auth-account-btn"),
    authHeaderLogoutBtn: document.getElementById("auth-header-logout-btn"),
    authButtonLabel: document.getElementById("auth-button-label"),
    authBackdrop: document.getElementById("auth-backdrop"),
    authModal: document.getElementById("auth-modal"),
    authCloseBtn: document.getElementById("auth-close-btn"),
    authForm: document.getElementById("auth-form"),
    authTitle: document.getElementById("auth-title"),
    authDescription: document.getElementById("auth-description"),
    authUsername: document.getElementById("auth-username"),
    authPassword: document.getElementById("auth-password"),
    authAlert: document.getElementById("auth-alert"),
    authSubmitBtn: document.getElementById("auth-submit-btn"),
    authSwitchBtn: document.getElementById("auth-switch-btn"),
    authGoogleSection: document.getElementById("auth-google-section"),
    authGoogleButton: document.getElementById("auth-google-button"),
    authGoogleFallbackBtn: document.getElementById("auth-google-fallback-btn"),
    authSignedIn: document.getElementById("auth-signed-in"),
    authCurrentUsername: document.getElementById("auth-current-username"),
    authLogoutBtn: document.getElementById("auth-logout-btn"),

    // Recommender Form
    form: document.getElementById("recommend-form"),
    comboSelect: document.getElementById("combination-select"),
    scoreGrid: document.getElementById("score-input-grid"),
    totalScoreDisplay: document.getElementById("total-score-display"),
    resetScoresBtn: document.getElementById("reset-scores-btn"),
    preferenceChoiceGroups: document.querySelectorAll("[data-preference-group]"),
    interestPreferenceCount: document.getElementById("interest-preference-count"),
    submitBtn: document.getElementById("submit-btn"),
    formAlert: document.getElementById("form-alert"),

    // Recommender Results
    resultsMeta: document.getElementById("results-meta"),
    resultScoreBadge: document.getElementById("result-score-badge"),
    profileSummary: document.getElementById("profile-summary"),
    filterTabsBar: document.getElementById("filter-tabs-bar"),
    tabPills: document.querySelectorAll(".tab-pill"),
    countAll: document.getElementById("count-all"),
    countSafe: document.getElementById("count-safe"),
    countMatch: document.getElementById("count-match"),
    countReach: document.getElementById("count-reach"),
    emptyState: document.getElementById("empty-state"),
    loadingState: document.getElementById("loading-state"),
    recContainer: document.getElementById("recommendations-container"),
    recList: document.getElementById("recommendations-list"),

    // Admissions Table
    admSearchInput: document.getElementById("adm-search-input"),
    admComboFilter: document.getElementById("adm-combo-filter"),
    admGroupFilter: document.getElementById("adm-group-filter"),
    admScaleFilter: document.getElementById("adm-scale-filter"),
    admSortFilter: document.getElementById("adm-sort-filter"),
    admTotalText: document.getElementById("adm-total-text"),
    admTbody: document.getElementById("admissions-tbody"),
    admPrevBtn: document.getElementById("adm-prev-btn"),
    admNextBtn: document.getElementById("adm-next-btn"),
    admPageIndicator: document.getElementById("adm-page-indicator"),

    // Career
    careerSectorsGrid: document.getElementById("career-sectors-grid"),
    careerSkillsGrid: document.getElementById("career-skills-grid"),

    // Wishlist Drawer
    openWishlistBtn: document.getElementById("open-wishlist-btn"),
    closeWishlistBtn: document.getElementById("close-wishlist-btn"),
    wishlistBackdrop: document.getElementById("wishlist-backdrop"),
    wishlistDrawer: document.getElementById("wishlist-drawer"),
    headerWishlistCount: document.getElementById("header-wishlist-count"),
    wishlistItemsContainer: document.getElementById("wishlist-items-container"),
    copyWishlistBtn: document.getElementById("copy-wishlist-btn"),
    clearWishlistBtn: document.getElementById("clear-wishlist-btn"),

    // Theme Toggle
    themeToggleBtn: document.getElementById("theme-toggle-btn"),
    themeIconMoon: document.getElementById("theme-icon-moon"),
    themeIconSun: document.getElementById("theme-icon-sun"),

    // Toast
    toast: document.getElementById("app-toast"),
  };

  /* ==========================================================================
     1. TOAST NOTIFICATIONS
     ========================================================================== */
  let toastTimer = null;
  function showToast(message) {
    if (toastTimer) clearTimeout(toastTimer);
    elements.toast.innerHTML = `${ICONS.check} <span>${escapeHtml(message)}</span>`;
    elements.toast.classList.remove("hidden");
    toastTimer = setTimeout(() => {
      elements.toast.classList.add("hidden");
    }, 2800);
  }

  /* ========================================================================
     1.1 AUTHENTICATION
     ======================================================================== */
  function renderAuthUi() {
    const signedIn = Boolean(state.auth.user);
    elements.authLoginBtn.classList.toggle("hidden", signedIn);
    elements.authRegisterBtn.classList.toggle("hidden", signedIn);
    elements.authAccountBtn.classList.toggle("hidden", !signedIn);
    elements.authHeaderLogoutBtn.classList.toggle("hidden", !signedIn);
    elements.authButtonLabel.textContent = signedIn ? state.auth.user.username : "";
    elements.authSignedIn.classList.toggle("hidden", !signedIn);
    elements.authForm.classList.toggle("hidden", signedIn);
    elements.authGoogleSection.classList.toggle("hidden", signedIn);
    elements.authGoogleFallbackBtn.classList.toggle("hidden", state.auth.googleEnabled);
    elements.authSwitchBtn.classList.toggle("hidden", signedIn);
    if (signedIn) {
      elements.authCurrentUsername.textContent = state.auth.user.username;
      return;
    }

    const registering = state.auth.mode === "register";
    elements.authTitle.textContent = registering ? "Tạo tài khoản" : "Đăng nhập";
    elements.authDescription.textContent = registering
      ? "Tạo tài khoản để sử dụng các tính năng cá nhân hóa."
      : "Đăng nhập để tiếp tục với tài khoản của bạn.";
    elements.authSubmitBtn.textContent = registering ? "Tạo tài khoản" : "Đăng nhập";
    elements.authSwitchBtn.textContent = registering ? "Đã có tài khoản? Đăng nhập" : "Chưa có tài khoản? Đăng ký";
    elements.authPassword.autocomplete = registering ? "new-password" : "current-password";
  }

  function showAuthError(message) {
    elements.authAlert.textContent = message;
    elements.authAlert.classList.remove("hidden");
  }

  function clearAuthError() {
    elements.authAlert.textContent = "";
    elements.authAlert.classList.add("hidden");
  }

  function loadGoogleIdentityScript() {
    if (window.google?.accounts?.id) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const existing = document.querySelector('script[src="https://accounts.google.com/gsi/client"]');
      if (existing) {
        existing.addEventListener("load", resolve, { once: true });
        existing.addEventListener("error", reject, { once: true });
        return;
      }
      const script = document.createElement("script");
      script.src = "https://accounts.google.com/gsi/client";
      script.async = true;
      script.defer = true;
      script.onload = resolve;
      script.onerror = reject;
      document.head.appendChild(script);
    });
  }

  async function handleGoogleCredential(response) {
    clearAuthError();
    try {
      const request = await fetch("/api/auth/google", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ credential: response.credential }),
      });
      const data = await request.json();
      if (!request.ok || !data.token || !data.user) throw new Error(data.message || "Không thể đăng nhập Google.");
      state.auth.token = data.token;
      state.auth.user = data.user;
      localStorage.setItem("dss_auth_token", data.token);
      renderAuthUi();
      closeAuthModal();
      showToast(data.message || "Đăng nhập Google thành công.");
    } catch (error) {
      showAuthError(error.message || "Không thể đăng nhập Google.");
    }
  }

  async function initializeGoogleAuth() {
    if (state.auth.googleInitialized || state.auth.user) return;
    try {
      const response = await fetch("/api/auth/config");
      const config = await response.json();
      if (!response.ok || !config.google_enabled || !config.google_client_id) return;
      await loadGoogleIdentityScript();
      window.google.accounts.id.initialize({
        client_id: config.google_client_id,
        callback: handleGoogleCredential,
        auto_select: false,
      });
      window.google.accounts.id.renderButton(elements.authGoogleButton, {
        type: "standard",
        theme: "outline",
        size: "large",
        text: "continue_with",
        shape: "rectangular",
        width: 320,
      });
      state.auth.googleEnabled = true;
      state.auth.googleInitialized = true;
      renderAuthUi();
    } catch (_) {
      // Password login stays available if Google Identity Services is unreachable.
    }
  }

  function openAuthModal(mode = state.auth.mode) {
    state.auth.mode = mode;
    clearAuthError();
    renderAuthUi();
    initializeGoogleAuth();
    elements.authBackdrop.classList.remove("hidden");
    elements.authModal.classList.remove("hidden");
    if (!state.auth.user) elements.authUsername.focus();
  }

  function closeAuthModal() {
    elements.authBackdrop.classList.add("hidden");
    elements.authModal.classList.add("hidden");
  }

  function signOut() {
    state.auth.token = null;
    state.auth.user = null;
    localStorage.removeItem("dss_auth_token");
    renderAuthUi();
    closeAuthModal();
    showToast("Đã đăng xuất.");
  }

  async function restoreSession() {
    if (!state.auth.token) {
      renderAuthUi();
      return;
    }
    try {
      const response = await fetch("/api/auth/me", {
        headers: { Authorization: `Bearer ${state.auth.token}` },
      });
      const data = await response.json();
      if (!response.ok || !data.user) throw new Error("invalid session");
      state.auth.user = data.user;
    } catch (_) {
      state.auth.token = null;
      localStorage.removeItem("dss_auth_token");
    }
    renderAuthUi();
  }

  elements.authLoginBtn.addEventListener("click", () => openAuthModal("login"));
  elements.authRegisterBtn.addEventListener("click", () => openAuthModal("register"));
  elements.authAccountBtn.addEventListener("click", () => openAuthModal());
  elements.authCloseBtn.addEventListener("click", closeAuthModal);
  elements.authBackdrop.addEventListener("click", closeAuthModal);
  elements.authSwitchBtn.addEventListener("click", () => {
    state.auth.mode = state.auth.mode === "login" ? "register" : "login";
    clearAuthError();
    renderAuthUi();
  });
  elements.authLogoutBtn.addEventListener("click", signOut);
  elements.authHeaderLogoutBtn.addEventListener("click", signOut);
  elements.authGoogleFallbackBtn.addEventListener("click", () => {
    showAuthError("Đăng nhập Google chưa được cấu hình. Hãy thêm GOOGLE_CLIENT_ID trên Render rồi deploy lại API.");
  });
  elements.authForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearAuthError();
    const username = elements.authUsername.value.trim();
    const password = elements.authPassword.value;
    const endpoint = state.auth.mode === "register" ? "/api/auth/register" : "/api/auth/login";
    elements.authSubmitBtn.disabled = true;
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const data = await response.json();
      if (!response.ok || !data.token || !data.user) throw new Error(data.message || "Không thể xác thực tài khoản.");
      state.auth.token = data.token;
      state.auth.user = data.user;
      localStorage.setItem("dss_auth_token", data.token);
      elements.authPassword.value = "";
      renderAuthUi();
      closeAuthModal();
      showToast(data.message || "Đăng nhập thành công.");
    } catch (error) {
      showAuthError(error.message || "Không thể kết nối đến dịch vụ tài khoản.");
    } finally {
      elements.authSubmitBtn.disabled = false;
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !elements.authModal.classList.contains("hidden")) closeAuthModal();
  });

  /* ==========================================================================
     2. NAVIGATION & TABS
     ========================================================================== */
  function switchView(targetViewId) {
    // Phiên bản tối giản chỉ duy trì một luồng: nhập điểm → nhận gợi ý.
    if (targetViewId !== "recommend") targetViewId = "recommend";
    state.activeView = targetViewId;
    elements.views.forEach((view) => {
      view.classList.toggle("active", view.id === `${targetViewId}-view`);
    });
    elements.navBtns.forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.nav === targetViewId);
    });
    window.location.hash = targetViewId;

    if (targetViewId === "admissions" && elements.admTbody.children.length === 0) {
      loadAdmissionsTable();
    } else if (targetViewId === "career" && !state.careerLoaded) {
      loadCareerInsights();
    }
  }

  elements.navBtns.forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      switchView(btn.dataset.nav);
    });
  });

  if (elements.brandLink) {
    elements.brandLink.addEventListener("click", (e) => {
      e.preventDefault();
      switchView("recommend");
    });
  }

  /* ==========================================================================
     3. RECOMMENDER: SCORE INPUTS
     ========================================================================== */
  function renderScoreInputs() {
    const selectedCombo = elements.comboSelect.value;
    const subjects = combinations[selectedCombo] || [];
    elements.scoreGrid.innerHTML = subjects
      .map(
        (subj) => `
      <div class="score-field">
        <label for="score-${subj}">${subjectNames[subj] || subj}</label>
        <input
          type="number"
          id="score-${subj}"
          name="${subj}"
          min="0"
          max="10"
          step="0.05"
          placeholder="0.00"
          inputmode="decimal"
          required
        />
      </div>
    `
      )
      .join("");

    elements.scoreGrid.querySelectorAll("input").forEach((input) => {
      input.addEventListener("input", updateTotalScoreDisplay);
    });
    updateTotalScoreDisplay();
  }

  function updateTotalScoreDisplay() {
    const inputs = elements.scoreGrid.querySelectorAll("input");
    if (!inputs.length) {
      elements.totalScoreDisplay.textContent = "—";
      return;
    }
    let sum = 0;
    let complete = true;
    inputs.forEach((input) => {
      const val = parseFloat(input.value);
      if (isNaN(val) || val < 0 || val > 10) {
        complete = false;
      } else {
        sum += val;
      }
    });

    if (complete) {
      elements.totalScoreDisplay.textContent = sum.toFixed(2);
    } else {
      elements.totalScoreDisplay.textContent = "—";
    }
  }

  function resetRecommendationForm() {
    elements.scoreGrid.querySelectorAll("input").forEach((input) => {
      input.value = "";
    });
    state.recommendations = null;
    elements.formAlert.classList.add("hidden");
    elements.resultsMeta.classList.add("hidden");
    elements.filterTabsBar.classList.add("hidden");
    elements.recContainer.classList.add("hidden");
    elements.loadingState.classList.add("hidden");
    elements.emptyState.classList.remove("hidden");
    updateTotalScoreDisplay();
  }

  elements.comboSelect.addEventListener("change", renderScoreInputs);
  elements.resetScoresBtn.addEventListener("click", resetRecommendationForm);

  /* Interest choices are persisted locally and sent with each recommendation request. */
  function loadStoredInterests() {
    try {
      const savedInterests = JSON.parse(localStorage.getItem("dss_user_interests") || "null");
      if (Array.isArray(savedInterests)) return migrateLegacyInterests(savedInterests);

      const legacyProfile = JSON.parse(localStorage.getItem("dss_user_profile") || "null");
      return Array.isArray(legacyProfile?.interests) ? migrateLegacyInterests(legacyProfile.interests) : [];
    } catch (_) {
      return [];
    }
  }

  // Chuyển nhãn nhóm ngành cũ sang câu mô tả sở thích hiện hành để nút và dữ
  // liệu gửi về backend luôn đồng nhất.
  function migrateLegacyInterests(interests) {
    const legacyInterestValues = {
      "Công nghệ": "Khám phá máy tính, dữ liệu & AI",
      "Công nghệ số": "Khám phá máy tính, dữ liệu & AI",
      "Máy tính, dữ liệu & AI": "Khám phá máy tính, dữ liệu & AI",
      "Kỹ thuật & xây dựng": "Thiết kế, chế tạo & xây dựng",
      "Máy móc, công trình & kỹ thuật": "Thiết kế, chế tạo & xây dựng",
      "Kinh doanh": "Kinh doanh & làm việc với thị trường",
      "Kinh doanh & thị trường": "Kinh doanh & làm việc với thị trường",
      "Sáng tạo": "Sáng tạo nội dung & thiết kế",
      "Nội dung, thiết kế & truyền thông": "Sáng tạo nội dung & thiết kế",
      "Xã hội & cộng đồng": "Làm việc với con người & cộng đồng",
      "Con người, cộng đồng & dịch vụ": "Làm việc với con người & cộng đồng",
    };
    return [...new Set(interests.map((interest) => legacyInterestValues[interest] || interest))];
  }

  function saveInterests() {
    localStorage.setItem("dss_user_interests", JSON.stringify(state.interests));
    localStorage.removeItem("dss_user_profile");
  }

  function syncPreferenceGroup(groupName) {
    const group = document.querySelector(`[data-preference-group="${groupName}"]`);
    if (!group) return;

    const selectedValues = state.interests;
    group.querySelectorAll(".preference-chip").forEach((button) => {
      const isSelected = selectedValues.includes(button.dataset.preferenceValue);
      button.classList.toggle("selected", isSelected);
      button.setAttribute("aria-pressed", String(isSelected));
    });

    if (elements.interestPreferenceCount) {
      elements.interestPreferenceCount.textContent = `${selectedValues.length}/2 đã chọn`;
    }
  }

  function syncProfileSummary() {
    const summaryParts = [...state.interests];

    if (!summaryParts.length) {
      elements.profileSummary.classList.add("hidden");
      elements.profileSummary.textContent = "";
      return;
    }

    elements.profileSummary.textContent = `Hồ sơ đã chọn: ${summaryParts.join(" · ")}`;
    elements.profileSummary.classList.remove("hidden");
  }

  function initPreferenceProfile() {
    if (!Array.isArray(state.interests)) state.interests = [];
    saveInterests();

    elements.preferenceChoiceGroups.forEach((group) => {
      const groupName = group.dataset.preferenceGroup;
      const maxSelections = Number(group.dataset.maxSelections || 2);

      group.querySelectorAll(".preference-chip").forEach((button) => {
        button.addEventListener("click", () => {
          const value = button.dataset.preferenceValue;
          const selections = state.interests;
          const existingIndex = selections.indexOf(value);

          if (existingIndex >= 0) {
            selections.splice(existingIndex, 1);
          } else if (selections.length < maxSelections) {
            selections.push(value);
          } else {
            showToast(`Bạn có thể chọn tối đa ${maxSelections} mục.`);
            return;
          }

          saveInterests();
          syncPreferenceGroup(groupName);
          syncProfileSummary();
        });
      });

      syncPreferenceGroup(groupName);
    });

    syncProfileSummary();
  }

  /* ==========================================================================
     4. RECOMMENDER: SUBMISSION & RENDERING
     ========================================================================== */
  elements.form.addEventListener("submit", async (e) => {
    e.preventDefault();
    elements.formAlert.classList.add("hidden");

    const combo = elements.comboSelect.value;
    const subjects = combinations[combo] || [];
    const scores = {};
    let hasError = false;

    subjects.forEach((subj) => {
      const input = document.getElementById(`score-${subj}`);
      const val = parseFloat(input ? input.value : "");
      if (isNaN(val) || val < 0 || val > 10) {
        hasError = true;
      } else {
        scores[subj] = val;
      }
    });

    if (hasError) {
      elements.formAlert.textContent = "Vui lòng nhập đầy đủ điểm từ 0 đến 10 cho cả 3 môn xét tuyển.";
      elements.formAlert.classList.remove("hidden");
      return;
    }

    // Prepare UI for loading
    elements.submitBtn.disabled = true;
    elements.submitBtn.querySelector("span").textContent = "Đang phân tích...";
    elements.emptyState.classList.add("hidden");
    elements.recContainer.classList.add("hidden");
    elements.loadingState.classList.remove("hidden");

    try {
      const response = await fetch("/api/recommend", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          combination: combo,
          scores: scores,
          interests: [...state.interests],
        }),
      });

      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Không thể phân tích kết quả lúc này.");

      state.recommendations = data;
      renderRecommendationResults(data);
    } catch (err) {
      elements.formAlert.textContent = err.message;
      elements.formAlert.classList.remove("hidden");
      elements.emptyState.classList.remove("hidden");
    } finally {
      elements.submitBtn.disabled = false;
      elements.submitBtn.querySelector("span").textContent = "Phân tích lộ trình trúng tuyển";
      elements.loadingState.classList.add("hidden");
    }
  });

  function renderRecommendationResults(data) {
    const { counts, user_score, combination } = data;

    // Update Counts & Badges
    elements.resultScoreBadge.textContent = `Điểm của bạn: ${user_score.toFixed(2)} (${combination})`;
    elements.resultsMeta.classList.remove("hidden");
    elements.filterTabsBar.classList.remove("hidden");

    elements.countAll.textContent = (counts.safe || 0) + (counts.match || 0) + (counts.reach || 0);
    elements.countSafe.textContent = counts.safe || 0;
    elements.countMatch.textContent = counts.match || 0;
    elements.countReach.textContent = counts.reach || 0;

    // Reset bucket filter to All
    state.activeBucket = "all";
    elements.tabPills.forEach((p) => p.classList.toggle("active", p.dataset.bucket === "all"));

    filterAndDisplayCards();
    elements.recContainer.classList.remove("hidden");
  }

  function filterAndDisplayCards() {
    if (!state.recommendations) return;
    const { results } = state.recommendations;
    let listToRender = [];

    if (state.activeBucket === "all") {
      // Merge all buckets: Safe first, then Match, then Reach
      (results.safe || []).forEach((item) => listToRender.push({ ...item, type: "safe" }));
      (results.match || []).forEach((item) => listToRender.push({ ...item, type: "match" }));
      (results.reach || []).forEach((item) => listToRender.push({ ...item, type: "reach" }));
    } else {
      (results[state.activeBucket] || []).forEach((item) => listToRender.push({ ...item, type: state.activeBucket }));
    }

    if (listToRender.length === 0) {
      const bucketLabels = { safe: "An toàn", match: "Phù hợp", reach: "Thử sức" };
      const emptyMessage = state.recommendations.total_count === 0
        ? state.recommendations.message || "Chưa tìm thấy ngành phù hợp với tổ hợp, mức điểm và sở thích đã chọn."
        : `Không có ngành nào thuộc nhóm ${bucketLabels[state.activeBucket] || "đã chọn"}.`;
      elements.recList.innerHTML = `
        <div class="empty-state-box" style="padding: 32px 16px;">
          <p class="empty-desc">${escapeHtml(emptyMessage)}</p>
        </div>
      `;
      return;
    }

    elements.recList.innerHTML = listToRender.map((item) => createRecommendationCardHtml(item)).join("");

    // Attach Wishlist buttons
    elements.recList.querySelectorAll(".btn-save-nv").forEach((btn) => {
      btn.addEventListener("click", () => {
        const major = btn.dataset.major;
        const school = btn.dataset.school;
        const cutoff = btn.dataset.cutoff;
        const code = btn.dataset.code;
        const gap = btn.dataset.gap;
        toggleWishlist({ major, school, cutoff, code, gap, logo_url: item.logo_url, logo_alt: item.logo_alt });
      });
    });
  }

  function schoolInitials(name) {
    const words = String(name || "").trim().split(/\s+/).filter(Boolean);
    if (!words.length) return "DH";
    const meaningful = words.filter((word) => !/^(trường|đại|học|học viện)$/i.test(word));
    const source = meaningful.length ? meaningful : words;
    return source.slice(-2).map((word) => word.charAt(0)).join("").toUpperCase();
  }

  function schoolAvatarHtml(item) {
    const name = item.school || item.school_name || "Trường đại học";
    const initials = schoolInitials(name);
    const fallbackClass = item.logo_url ? "school-avatar-fallback hidden" : "school-avatar-fallback";
    const logo = item.logo_url
      ? `<img class="school-avatar-image" src="${escapeHtml(item.logo_url)}" alt="${escapeHtml(item.logo_alt || `Logo ${name}`)}" onload="if (this.naturalWidth > this.naturalHeight * 1.8) this.parentElement.classList.add('school-avatar--wide');" onerror="this.classList.add('hidden'); this.nextElementSibling.classList.remove('hidden');" />`
      : "";
    return `<span class="school-avatar" aria-hidden="${item.logo_url ? "false" : "true"}">${logo}<span class="${fallbackClass}">${escapeHtml(initials)}</span></span>`;
  }

  function createRecommendationCardHtml(item) {
    const isSaved = isItemInWishlist(item.school, item.major);
    const gapSign = item.gap > 0 ? `+${item.gap.toFixed(2)}` : `${item.gap.toFixed(2)}`;
    const typeLabel = item.type === "safe" ? "An toàn" : item.type === "match" ? "Phù hợp" : "Thử sức";
    const historicalCutoff = Number(item.historical_cutoff_2024 ?? item.cutoff);
    const forecastCutoff = Number(item.cutoff);
    const isModelForecast = item.forecast_source === "xgboost_cutoff_v1";
    const forecastYear = item.forecast_year || "2024";
    const forecastLabel = isModelForecast ? `Dự báo điểm ${forecastYear}` : "Điểm chuẩn 2024";
    const forecastTag = isModelForecast ? `Dự báo ${forecastYear}` : "Dữ liệu 2024";
    const recommendationScore = Number(item.recommendation_score || 0).toFixed(1);
    const interestFit = Number(item.interest_fit || 0).toFixed(0);
    const interestFitLabel = item.interest_fit_active ? ` Khớp sở thích ${interestFit}%.` : "";
    const saveIcon = isSaved
      ? `${ICONS.check} <span>Đã lưu NV</span>`
      : `${ICONS.plus} <span>Lưu NV</span>`;

    return `
      <article class="rec-card rec-card-v2" data-type="${item.type}">
        <div class="rec-card-top">
          <div class="rec-card-tags">
            <span class="badge ${item.type}">${typeLabel}</span>
            <span class="badge-tag">${escapeHtml(item.group || "Đại học")}</span>
            <span class="badge-tag">Mã: ${escapeHtml(item.major_code)}</span>
            <span class="badge-tag badge-model">${escapeHtml(forecastTag)}</span>
          </div>
          <button
            type="button"
            class="btn-save-nv ${isSaved ? "saved" : ""}"
            data-major="${escapeHtml(item.major)}"
            data-school="${escapeHtml(item.school)}"
            data-code="${escapeHtml(item.major_code)}"
            data-cutoff="${forecastCutoff.toFixed(2)}"
            data-gap="${gapSign}"
            aria-label="Lưu vào danh sách nguyện vọng"
          >
            ${saveIcon}
          </button>
        </div>

        <div class="rec-card-info">
          <h3 class="rec-major-title" title="${escapeHtml(item.major)}">${escapeHtml(item.major)}</h3>
          <p class="rec-school-name" title="${escapeHtml(item.school)}">
            ${schoolAvatarHtml(item)}
            <span>${escapeHtml(item.school)}</span>
          </p>
        </div>

        <div class="rec-card-metrics">
          <div class="metric-block">
            <span class="metric-label">Điểm chuẩn 2024</span>
            <span class="metric-value">${historicalCutoff.toFixed(2)}</span>
          </div>

          <div class="metric-block metric-block-forecast">
            <span class="metric-label">${forecastLabel}</span>
            <span class="metric-value">${forecastCutoff.toFixed(2)}</span>
          </div>

          <div class="metric-block">
            <span class="metric-label">Chênh lệch với điểm bạn</span>
            <span class="gap-pill ${item.type}">${gapSign} đ</span>
          </div>

          <div class="metric-block metric-block-fit">
            <span class="metric-label">Độ phù hợp</span>
            <span class="metric-value metric-fit-score">${recommendationScore}<small>/100</small></span>
          </div>
        </div>

        <div class="rec-card-footer">
          <svg class="ui-icon ui-icon-sm" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
          <span>Gợi ý dựa trên điểm xét tuyển, mốc điểm dự kiến và cơ hội việc làm.${interestFitLabel}</span>
        </div>
      </article>
    `;
  }

  // Bucket Filter Pills
  elements.tabPills.forEach((pill) => {
    pill.addEventListener("click", () => {
      elements.tabPills.forEach((p) => p.classList.remove("active"));
      pill.classList.add("active");
      state.activeBucket = pill.dataset.bucket;
      filterAndDisplayCards();
    });
  });

  /* ==========================================================================
     5. VIEW 2: ADMISSIONS TABLE LOOKUP
     ========================================================================== */
  let searchDebounceTimer = null;

  function loadAdmissionsTable() {
    state.admissionsSearch.loading = true;
    elements.admTbody.innerHTML = `
      <tr>
        <td colspan="8" style="text-align: center; padding: 40px; color: var(--text-secondary);">
          <div class="flat-spinner" style="margin-bottom: 8px;"></div>
          Đang tải dữ liệu điểm chuẩn...
        </td>
      </tr>
    `;

    const params = new URLSearchParams({
      q: state.admissionsSearch.q,
      combination: state.admissionsSearch.combination,
      group: state.admissionsSearch.group,
      scale: state.admissionsSearch.scale,
      sort: state.admissionsSearch.sort,
      page: state.admissionsSearch.page,
      limit: state.admissionsSearch.limit,
    });

    fetch(`/api/admissions/search?${params.toString()}`)
      .then((res) => res.json())
      .then((data) => {
        state.admissionsSearch.total = data.total;
        state.admissionsSearch.pages = data.pages;
        renderAdmissionsTable(data);
      })
      .catch((err) => {
        elements.admTbody.innerHTML = `
          <tr>
            <td colspan="8" style="text-align: center; color: var(--danger-text); padding: 30px;">
              Lỗi tải dữ liệu điểm chuẩn: ${escapeHtml(err.message)}
            </td>
          </tr>
        `;
      })
      .finally(() => {
        state.admissionsSearch.loading = false;
      });
  }

  function renderAdmissionsTable(data) {
    const { items, total, page, pages } = data;
    elements.admTotalText.textContent = `Tìm thấy ${new Intl.NumberFormat("vi-VN").format(total)} bản ghi xét tuyển 2024`;
    elements.admPageIndicator.textContent = `Trang ${page} / ${pages || 1}`;
    elements.admPrevBtn.disabled = page <= 1;
    elements.admNextBtn.disabled = page >= pages;

    if (!items || items.length === 0) {
      elements.admTbody.innerHTML = `
        <tr>
          <td colspan="8" style="text-align: center; padding: 40px; color: var(--text-muted);">
            Không tìm thấy ngành hoặc trường phù hợp với tiêu chí lọc.
          </td>
        </tr>
      `;
      return;
    }

    elements.admTbody.innerHTML = items
      .map((row) => {
        const isSaved = isItemInWishlist(row.school, row.major);
        const saveIcon = isSaved
          ? `${ICONS.check} <span>Đã lưu</span>`
          : `${ICONS.plus} <span>Lưu</span>`;
        return `
        <tr>
          <td><strong>${escapeHtml(row.school_code)}</strong></td>
          <td style="font-weight: 600;"><span class="school-table-cell">${schoolAvatarHtml(row)}<span>${escapeHtml(row.school)}</span></span></td>
          <td><strong>${escapeHtml(row.major)}</strong></td>
          <td style="color: var(--text-secondary);">${escapeHtml(row.major_code)}</td>
          <td><span class="badge-tag">${escapeHtml(row.combination)}</span></td>
          <td class="td-cutoff">${row.cutoff.toFixed(2)}</td>
          <td style="font-size: 12px; color: var(--text-secondary);">${escapeHtml(row.note || row.scale)}</td>
          <td class="td-action">
            <button
              type="button"
              class="btn-save-nv ${isSaved ? "saved" : ""}"
              data-major="${escapeHtml(row.major)}"
              data-school="${escapeHtml(row.school)}"
              data-code="${escapeHtml(row.major_code)}"
              data-cutoff="${row.cutoff.toFixed(2)}"
              data-gap=""
              aria-label="Lưu vào danh sách nguyện vọng"
            >
              ${saveIcon}
            </button>
          </td>
        </tr>
      `;
      })
      .join("");

    // Attach wishlist buttons on table
    elements.admTbody.querySelectorAll(".btn-save-nv").forEach((btn) => {
      btn.addEventListener("click", () => {
        const major = btn.dataset.major;
        const school = btn.dataset.school;
        const cutoff = btn.dataset.cutoff;
        const code = btn.dataset.code;
        toggleWishlist({ major, school, cutoff, code, gap: "", logo_url: row.logo_url, logo_alt: row.logo_alt });
      });
    });
  }

  // Filter events for Admissions Search
  elements.admSearchInput.addEventListener("input", (e) => {
    clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(() => {
      state.admissionsSearch.q = e.target.value.trim();
      state.admissionsSearch.page = 1;
      loadAdmissionsTable();
    }, 300);
  });

  elements.admComboFilter.addEventListener("change", (e) => {
    state.admissionsSearch.combination = e.target.value;
    state.admissionsSearch.page = 1;
    loadAdmissionsTable();
  });

  elements.admGroupFilter.addEventListener("change", (e) => {
    state.admissionsSearch.group = e.target.value;
    state.admissionsSearch.page = 1;
    loadAdmissionsTable();
  });

  elements.admScaleFilter.addEventListener("change", (e) => {
    state.admissionsSearch.scale = e.target.value;
    state.admissionsSearch.page = 1;
    loadAdmissionsTable();
  });

  elements.admSortFilter.addEventListener("change", (e) => {
    state.admissionsSearch.sort = e.target.value;
    state.admissionsSearch.page = 1;
    loadAdmissionsTable();
  });

  elements.admPrevBtn.addEventListener("click", () => {
    if (state.admissionsSearch.page > 1) {
      state.admissionsSearch.page -= 1;
      loadAdmissionsTable();
    }
  });

  elements.admNextBtn.addEventListener("click", () => {
    if (state.admissionsSearch.page < state.admissionsSearch.pages) {
      state.admissionsSearch.page += 1;
      loadAdmissionsTable();
    }
  });

  /* ==========================================================================
     6. VIEW 3: CAREER INSIGHTS
     ========================================================================== */
  function loadCareerInsights() {
    fetch("/api/career/insights")
      .then((res) => res.json())
      .then((data) => {
        state.careerLoaded = true;
        renderCareerInsights(data);
      })
      .catch((err) => {
        console.error("Lỗi tải thông tin thị trường nghề:", err);
      });
  }

  function renderCareerInsights(data) {
    const { sectors, in_demand_skills } = data;

    // Sectors Grid
    elements.careerSectorsGrid.innerHTML = sectors
      .map(
        (sec) => `
      <article class="career-sector-card">
        <div class="career-sector-head">
          <div style="display: flex; align-items: center; gap: 8px;">
            ${ICONS.sectors[sec.icon] || ICONS.school}
            <h3>${escapeHtml(sec.name)}</h3>
          </div>
          <span class="demand-badge ${sec.demand === "Rất cao" || sec.demand === "Cao" ? "high" : "steady"}">
            Nhu cầu: ${escapeHtml(sec.demand)}
          </span>
        </div>

        <div class="career-salary-box">
          <span class="career-salary-label">Lương trung bình / trung vị:</span>
          <span class="career-salary-val">${escapeHtml(String(sec.average_salary_million_vnd))} / ${escapeHtml(String(sec.median_salary_million_vnd))} triệu VNĐ</span>
        </div>

        <div class="career-section-sub">Dữ liệu tuyển dụng ghi nhận</div>
        <div class="career-tags-wrap">
          <span class="badge-tag">${escapeHtml(String(sec.posting_count))} tin tuyển dụng</span>
          <span class="badge-tag">Kinh nghiệm TB: ${escapeHtml(String(sec.average_experience_months))} tháng</span>
        </div>

        <div class="career-section-sub">Kỹ năng nhà tuyển dụng săn đón</div>
        <div class="career-tags-wrap">
          ${sec.skills.map((s) => `<span class="badge-tag" style="background-color: var(--primary-light); color: var(--primary); font-weight: 600;">${escapeHtml(s)}</span>`).join("")}
        </div>
      </article>
    `
      )
      .join("");

    // Skills Grid
    elements.careerSkillsGrid.innerHTML = in_demand_skills
      .map(
        (item) => `
      <div class="skill-highlight-item">
        <strong>${escapeHtml(item.skill)}</strong>
        <p>${escapeHtml(item.level)}</p>
      </div>
    `
      )
      .join("");
  }

  /* ==========================================================================
     7. WISHLIST MANAGEMENT (DANH SÁCH NGUYỆN VỌNG)
     ========================================================================== */
  function isItemInWishlist(school, major) {
    return state.wishlist.some((item) => item.school === school && item.major === major);
  }

  function toggleWishlist(item) {
    const index = state.wishlist.findIndex((w) => w.school === item.school && w.major === item.major);
    if (index > -1) {
      state.wishlist.splice(index, 1);
      showToast(`Đã bỏ khỏi danh sách nguyện vọng: ${item.major}`);
    } else {
      state.wishlist.push(item);
      showToast(`Đã thêm vào nguyện vọng: ${item.major} - ${item.school}`);
    }
    saveWishlist();
    updateWishlistUi();
    refreshCardButtons();
  }

  function saveWishlist() {
    localStorage.setItem("dss_user_wishlist", JSON.stringify(state.wishlist));
  }

  function updateWishlistUi() {
    const count = state.wishlist.length;
    elements.headerWishlistCount.textContent = count;

    if (count === 0) {
      elements.wishlistItemsContainer.innerHTML = `
        <div class="drawer-empty-state">
          ${ICONS.bookmark}
          <p>Bạn chưa lưu nguyện vọng nào.<br>Bấm <strong>+ Lưu NV</strong> trên các ngành gợi ý để thêm vào đây.</p>
        </div>
      `;
      return;
    }

    elements.wishlistItemsContainer.innerHTML = state.wishlist
      .map((item, idx) => `
        <div class="drawer-item">
          <span class="drawer-item-index">NV${idx + 1}</span>
          <div class="drawer-item-info">
            <h4 class="drawer-item-major" title="${escapeHtml(item.major)}">${escapeHtml(item.major)}</h4>
            <p class="drawer-item-school" title="${escapeHtml(item.school)}">${schoolAvatarHtml(item)}<span>${escapeHtml(item.school)}</span></p>
          </div>
          <div class="drawer-item-scores">
            ${item.cutoff ? `${item.cutoff}đ` : ""}
          </div>
          <div class="drawer-item-actions">
            ${idx > 0 ? `<button type="button" class="drawer-item-btn" data-move-up="${idx}" title="Đẩy lên NV trên">${ICONS.arrowUp}</button>` : ""}
            ${idx < count - 1 ? `<button type="button" class="drawer-item-btn" data-move-down="${idx}" title="Đẩy xuống NV dưới">${ICONS.arrowDown}</button>` : ""}
            <button type="button" class="drawer-item-btn remove" data-remove="${idx}" title="Xóa">${ICONS.close}</button>
          </div>
        </div>
      `)
      .join("");

    // Attach reorder and remove actions
    elements.wishlistItemsContainer.querySelectorAll("[data-move-up]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const i = parseInt(btn.dataset.moveUp, 10);
        const temp = state.wishlist[i];
        state.wishlist[i] = state.wishlist[i - 1];
        state.wishlist[i - 1] = temp;
        saveWishlist();
        updateWishlistUi();
      });
    });

    elements.wishlistItemsContainer.querySelectorAll("[data-move-down]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const i = parseInt(btn.dataset.moveDown, 10);
        const temp = state.wishlist[i];
        state.wishlist[i] = state.wishlist[i + 1];
        state.wishlist[i + 1] = temp;
        saveWishlist();
        updateWishlistUi();
      });
    });

    elements.wishlistItemsContainer.querySelectorAll("[data-remove]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const i = parseInt(btn.dataset.remove, 10);
        state.wishlist.splice(i, 1);
        saveWishlist();
        updateWishlistUi();
        refreshCardButtons();
      });
    });
  }

  function refreshCardButtons() {
    document.querySelectorAll(".btn-save-nv").forEach((btn) => {
      const major = btn.dataset.major;
      const school = btn.dataset.school;
      const isSaved = isItemInWishlist(school, major);
      btn.classList.toggle("saved", isSaved);
      btn.innerHTML = isSaved
        ? `${ICONS.check} <span>Đã lưu NV</span>`
        : `${ICONS.plus} <span>Lưu NV</span>`;
    });
  }

  // Drawer Toggle
  function openWishlistDrawer() {
    updateWishlistUi();
    elements.wishlistBackdrop.classList.remove("hidden");
    elements.wishlistDrawer.classList.add("open");
    elements.wishlistDrawer.setAttribute("aria-hidden", "false");
  }

  function closeWishlistDrawer() {
    elements.wishlistBackdrop.classList.add("hidden");
    elements.wishlistDrawer.classList.remove("open");
    elements.wishlistDrawer.setAttribute("aria-hidden", "true");
  }

  elements.openWishlistBtn.addEventListener("click", openWishlistDrawer);
  elements.closeWishlistBtn.addEventListener("click", closeWishlistDrawer);
  elements.wishlistBackdrop.addEventListener("click", closeWishlistDrawer);

  // Copy wishlist as text
  elements.copyWishlistBtn.addEventListener("click", () => {
    if (state.wishlist.length === 0) {
      showToast("Danh sách nguyện vọng đang trống!");
      return;
    }
    const textLines = [
      "=== DANH SÁCH NGUYỆN VỌNG DỰ KIẾN (LA BÀN ĐẠI HỌC) ===",
      ...state.wishlist.map(
        (item, idx) => `NV${idx + 1}: ${item.major} - ${item.school} (Điểm chuẩn 2024: ${item.cutoff}đ)`
      ),
      "==================================================",
    ];
    const fullText = textLines.join("\n");
    navigator.clipboard
      .writeText(fullText)
      .then(() => {
        showToast("Đã sao chép danh sách nguyện vọng!");
      })
      .catch(() => {
        showToast("Không thể tự động sao chép. Vui lòng thử lại!");
      });
  });

  elements.clearWishlistBtn.addEventListener("click", () => {
    if (confirm("Bạn có chắc chắn muốn xóa toàn bộ danh sách nguyện vọng đã lưu?")) {
      state.wishlist = [];
      saveWishlist();
      updateWishlistUi();
      refreshCardButtons();
      showToast("Đã làm trống danh sách nguyện vọng.");
    }
  });

  /* ==========================================================================
     8. DARK / LIGHT THEME TOGGLE
     ========================================================================== */
  function initTheme() {
    // Không kế thừa thiết lập giao diện của bản nhiều màn hình trước đây.
    const savedTheme = localStorage.getItem("dss_minimal_theme");
    const isDark = savedTheme ? savedTheme === "dark" : true;

    applyTheme(isDark);
  }

  function applyTheme(isDark) {
    document.body.classList.toggle("dark-mode", isDark);
    elements.themeIconMoon.classList.toggle("hidden", isDark);
    elements.themeIconSun.classList.toggle("hidden", !isDark);
    localStorage.setItem("dss_minimal_theme", isDark ? "dark" : "light");
  }

  elements.themeToggleBtn.addEventListener("click", () => {
    const isCurrentlyDark = document.body.classList.contains("dark-mode");
    applyTheme(!isCurrentlyDark);
  });

  /* ==========================================================================
     9. UTILITY: ESCAPE HTML
     ========================================================================== */
  function escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  /* ==========================================================================
     10. INITIALIZATION
     ========================================================================== */
  initTheme();
  renderScoreInputs();
  initPreferenceProfile();
  updateWishlistUi();
  restoreSession();

  // Check URL hash for direct tab navigation
  const hash = window.location.hash.replace("#", "");
  if (["recommend", "admissions", "career", "about"].includes(hash)) {
    switchView(hash);
  } else {
    switchView("recommend");
  }
})();
