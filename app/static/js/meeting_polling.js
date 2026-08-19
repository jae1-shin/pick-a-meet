(() => {
  const content = document.querySelector("#meeting-list-content[data-refresh-url]");
  if (!content) return;

  const interval = Number(content.dataset.refreshInterval) || 5000;
  let submitting = false;
  let requestSequence = 0;
  let activeController = null;
  let pinnedMeetingId = null;

  const tooltipIsInUse = () => Boolean(
    content.querySelector(
      ".applicant-tooltip:hover, .applicant-tooltip:focus-within, .applicant-tooltip.pinned"
    )
  );

  const restorePinnedTooltip = () => {
    content.querySelectorAll(".applicant-tooltip.pinned").forEach((tooltip) => {
      tooltip.classList.remove("pinned");
    });
    if (pinnedMeetingId === null) return;
    const tooltip = content.querySelector(
      `.applicant-tooltip[data-meeting-id="${pinnedMeetingId}"]`
    );
    if (!tooltip) {
      pinnedMeetingId = null;
      return;
    }
    tooltip.classList.add("pinned");
  };

  content.addEventListener("submit", () => {
    submitting = true;
  });

  const refresh = async ({ force = false } = {}) => {
    if (submitting || (!force && (document.hidden || tooltipIsInUse()))) return;
    if (activeController) {
      if (!force) return;
      activeController.abort();
    }
    const controller = new AbortController();
    const sequence = ++requestSequence;
    activeController = controller;
    try {
      const response = await fetch(content.dataset.refreshUrl, {
        cache: "no-store",
        credentials: "same-origin",
        headers: { "X-Requested-With": "meeting-polling" },
        signal: controller.signal,
      });
      if (response.status === 401 || response.status === 403 || response.status === 409) {
        window.location.reload();
        return;
      }
      if (!response.ok) return;
      const html = await response.text();
      if (!force && tooltipIsInUse()) return;
      if (!submitting && sequence === requestSequence) {
        content.innerHTML = html;
        restorePinnedTooltip();
      }
    } catch (_) {
      // 일시적인 네트워크 오류에는 현재 화면을 유지하고 다음 주기에 재시도한다.
    } finally {
      if (activeController === controller) activeController = null;
    }
  };

  content.addEventListener("click", (event) => {
    const trigger = event.target.closest(".tooltip-trigger");
    if (!trigger) return;
    const tooltip = trigger.closest(".applicant-tooltip[data-meeting-id]");
    const meetingId = tooltip.dataset.meetingId;
    pinnedMeetingId = pinnedMeetingId === meetingId ? null : meetingId;
    restorePinnedTooltip();
  });

  document.addEventListener("click", (event) => {
    if (event.target.closest(".applicant-tooltip")) return;
    pinnedMeetingId = null;
    restorePinnedTooltip();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    pinnedMeetingId = null;
    restorePinnedTooltip();
  });

  document.querySelector(".meeting-filters")?.addEventListener("click", (event) => {
    const chip = event.target.closest("[data-availability-filter]");
    if (!chip) return;
    event.preventDefault();

    const value = chip.dataset.availabilityFilter;
    const refreshUrl = new URL(content.dataset.refreshUrl, window.location.origin);
    const pageUrl = new URL(window.location.href);
    if (value === "all") {
      refreshUrl.searchParams.delete("availability");
      pageUrl.searchParams.delete("availability");
    } else {
      refreshUrl.searchParams.set("availability", value);
      pageUrl.searchParams.set("availability", value);
    }
    content.dataset.refreshUrl = `${refreshUrl.pathname}${refreshUrl.search}`;
    window.history.replaceState({}, "", `${pageUrl.pathname}${pageUrl.search}`);

    document.querySelectorAll("[data-availability-filter]").forEach((option) => {
      const selected = option === chip;
      option.classList.toggle("active", selected);
      option.setAttribute("aria-pressed", String(selected));
    });
    refresh({ force: true });
  });

  window.setInterval(refresh, interval);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refresh();
  });
})();
