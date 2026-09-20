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
    profile: JSON.parse(localStorage.getItem("dss_user_profile") || '{"interests":[],"priorities":[],"region":""}'),
  };

  // DOM Elements
  const elements = {
    // Nav
    navBtns: document.querySelectorAll(".nav-btn"),
    views: document.querySelectorAll(".app-view"),
    brandLink: document.querySelector(".brand"),

    // Recommender Form
    form: document.getElementById("recommend-form"),
    comboSelect: document.getElementById("combination-select"),
    scoreGrid: document.getElementById("score-input-grid"),
    totalScoreDisplay: document.getElementById("total-score-display"),
    groupFilter: document.getElementById("group-filter"),
    interestInput: document.getElementById("interest-input"),
    preferenceChoiceGroups: document.querySelectorAll("[data-preference-group]"),
    interestPreferenceCount: document.getElementById("interest-preference-count"),
    priorityPreferenceCount: document.getElementById("priority-preference-count"),
    regionPreference: document.getElementById("region-preference"),
    submitBtn: document.getElementById("submit-btn"),
    formAlert: document.getElementById("form-alert"),
    presetBtns: document.querySelectorAll(".preset-btn"),

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

  /* ==========================================================================
     2. NAVIGATION & TABS
     ========================================================================== */
  function switchView(targetViewId) {
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
     3. RECOMMENDER: SCORE INPUTS & PRESETS
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

  function applyPreset(presetType) {
    const inputs = elements.scoreGrid.querySelectorAll("input");
    if (presetType === "reset") {
      inputs.forEach((input) => (input.value = ""));
    } else if (presetType === "high") {
      inputs.forEach((input) => (input.value = "9.00"));
    } else if (presetType === "good") {
      inputs.forEach((input) => (input.value = "8.00"));
    } else if (presetType === "avg") {
      inputs.forEach((input) => (input.value = "7.00"));
    }
    updateTotalScoreDisplay();
    elements.formAlert.classList.add("hidden");
  }

  elements.presetBtns.forEach((btn) => {
    btn.addEventListener("click", () => applyPreset(btn.dataset.preset));
  });

  elements.comboSelect.addEventListener("change", renderScoreInputs);

  /* Preference choices are intentionally stored locally until the API ranks by them. */
  function saveProfile() {
    localStorage.setItem("dss_user_profile", JSON.stringify(state.profile));
  }

  function syncPreferenceGroup(groupName) {
    const group = document.querySelector(`[data-preference-group="${groupName}"]`);
    if (!group) return;

    const selectedValues = state.profile[groupName] || [];
    group.querySelectorAll(".preference-chip").forEach((button) => {
      const isSelected = selectedValues.includes(button.dataset.preferenceValue);
      button.classList.toggle("selected", isSelected);
      button.setAttribute("aria-pressed", String(isSelected));
    });

    const countElement = groupName === "interests" ? elements.interestPreferenceCount : elements.priorityPreferenceCount;
    if (countElement) countElement.textContent = `${selectedValues.length}/2 đã chọn`;
  }

  function syncProfileSummary() {
    const summaryParts = [...state.profile.interests, ...state.profile.priorities];
    if (state.profile.region) summaryParts.push(state.profile.region);

    if (!summaryParts.length) {
      elements.profileSummary.classList.add("hidden");
      elements.profileSummary.textContent = "";
      return;
    }

    elements.profileSummary.textContent = `Hồ sơ đã chọn: ${summaryParts.join(" · ")}`;
    elements.profileSummary.classList.remove("hidden");
  }

  function initPreferenceProfile() {
    if (!Array.isArray(state.profile.interests)) state.profile.interests = [];
    if (!Array.isArray(state.profile.priorities)) state.profile.priorities = [];
    if (typeof state.profile.region !== "string") state.profile.region = "";

    elements.preferenceChoiceGroups.forEach((group) => {
      const groupName = group.dataset.preferenceGroup;
      const maxSelections = Number(group.dataset.maxSelections || 2);

      group.querySelectorAll(".preference-chip").forEach((button) => {
        button.addEventListener("click", () => {
          const value = button.dataset.preferenceValue;
          const selections = state.profile[groupName];
          const existingIndex = selections.indexOf(value);

          if (existingIndex >= 0) {
            selections.splice(existingIndex, 1);
          } else if (selections.length < maxSelections) {
            selections.push(value);
          } else {
            showToast(`Bạn có thể chọn tối đa ${maxSelections} mục.`);
            return;
          }

          saveProfile();
          syncPreferenceGroup(groupName);
          syncProfileSummary();
        });
      });

      syncPreferenceGroup(groupName);
    });

    if (elements.regionPreference) {
      elements.regionPreference.value = state.profile.region;
      elements.regionPreference.addEventListener("change", () => {
        state.profile.region = elements.regionPreference.value;
        saveProfile();
        syncProfileSummary();
      });
    }

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
          group: elements.groupFilter.value,
          interest: elements.interestInput.value,
          preferences: state.profile,
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
      elements.recList.innerHTML = `
        <div class="empty-state-box" style="padding: 32px 16px;">
          <p class="empty-desc">Không tìm thấy ngành nào phù hợp với bộ lọc trong nhóm này.</p>
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
        toggleWishlist({ major, school, cutoff, code, gap });
      });
    });
  }

  function createRecommendationCardHtml(item) {
    const isSaved = isItemInWishlist(item.school, item.major);
    const gapSign = item.gap > 0 ? `+${item.gap.toFixed(2)}` : `${item.gap.toFixed(2)}`;
    const typeLabel = item.type === "safe" ? "An toàn" : item.type === "match" ? "Phù hợp" : "Thử sức";
    const saveIcon = isSaved
      ? `${ICONS.check} <span>Đã lưu NV</span>`
      : `${ICONS.plus} <span>Lưu NV</span>`;

    return `
      <article class="rec-card">
        <div class="rec-card-main">
          <div class="rec-card-tags">
            <span class="badge ${item.type}">${typeLabel}</span>
            <span class="badge-tag">${escapeHtml(item.group || "Đại học")}</span>
            <span class="badge-tag">Mã: ${escapeHtml(item.major_code)}</span>
          </div>
          <h3 class="rec-major-title" title="${escapeHtml(item.major)}">${escapeHtml(item.major)}</h3>
          <p class="rec-school-name" title="${escapeHtml(item.school)}">
            ${ICONS.school}
            <span>${escapeHtml(item.school)}</span>
          </p>
        </div>

        <div class="rec-card-scores">
          <div class="score-block">
            <span class="score-block-label">Điểm chuẩn 2024</span>
            <span class="score-block-val">${item.cutoff.toFixed(2)}</span>
          </div>

          <div class="score-block">
            <span class="score-block-label">Chênh lệch</span>
            <span class="gap-pill ${item.type}">${gapSign} đ</span>
          </div>

          <button
            type="button"
            class="btn-save-nv ${isSaved ? "saved" : ""}"
            data-major="${escapeHtml(item.major)}"
            data-school="${escapeHtml(item.school)}"
            data-code="${escapeHtml(item.major_code)}"
            data-cutoff="${item.cutoff.toFixed(2)}"
            data-gap="${gapSign}"
            aria-label="Lưu vào danh sách nguyện vọng"
          >
            ${saveIcon}
          </button>
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
          <td style="font-weight: 600;">${escapeHtml(row.school)}</td>
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
        toggleWishlist({ major, school, cutoff, code, gap: "" });
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
          <span class="career-salary-label">Mức lương tham khảo:</span>
          <span class="career-salary-val">${escapeHtml(sec.salary_range)}</span>
        </div>

        <div class="career-section-sub">Vị trí công việc tiêu biểu</div>
        <div class="career-tags-wrap">
          ${sec.roles.map((r) => `<span class="badge-tag">${escapeHtml(r)}</span>`).join("")}
        </div>

        <div class="career-section-sub">Kỹ năng nhà tuyển dụng săn đón</div>
        <div class="career-tags-wrap">
          ${sec.skills.map((s) => `<span class="badge-tag" style="background-color: var(--primary-light); color: var(--primary); font-weight: 600;">${escapeHtml(s)}</span>`).join("")}
        </div>

        <p class="career-desc-note">${escapeHtml(sec.highlight)}</p>
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
            <p class="drawer-item-school" title="${escapeHtml(item.school)}">${escapeHtml(item.school)}</p>
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
    const savedTheme = localStorage.getItem("dss_theme");
    const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    const isDark = savedTheme === "dark" || (!savedTheme && prefersDark);

    applyTheme(isDark);
  }

  function applyTheme(isDark) {
    document.body.classList.toggle("dark-mode", isDark);
    elements.themeIconMoon.classList.toggle("hidden", isDark);
    elements.themeIconSun.classList.toggle("hidden", !isDark);
    localStorage.setItem("dss_theme", isDark ? "dark" : "light");
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

  // Check URL hash for direct tab navigation
  const hash = window.location.hash.replace("#", "");
  if (["recommend", "admissions", "career", "about"].includes(hash)) {
    switchView(hash);
  } else {
    switchView("recommend");
  }
})();
