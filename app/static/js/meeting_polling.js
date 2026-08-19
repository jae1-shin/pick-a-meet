(() => {
  const content = document.querySelector("#meeting-list-content[data-refresh-url]");
  if (!content) return;

  const interval = Number(content.dataset.refreshInterval) || 5000;
  let refreshing = false;
  let submitting = false;

  content.addEventListener("submit", () => {
    submitting = true;
  });

  const refresh = async () => {
    if (refreshing || submitting || document.hidden) return;
    refreshing = true;
    try {
      const response = await fetch(content.dataset.refreshUrl, {
        cache: "no-store",
        credentials: "same-origin",
        headers: { "X-Requested-With": "meeting-polling" },
      });
      if (response.status === 401 || response.status === 403 || response.status === 409) {
        window.location.reload();
        return;
      }
      if (!response.ok) return;
      const html = await response.text();
      if (!submitting) content.innerHTML = html;
    } catch (_) {
      // 일시적인 네트워크 오류에는 현재 화면을 유지하고 다음 주기에 재시도한다.
    } finally {
      refreshing = false;
    }
  };

  window.setInterval(refresh, interval);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refresh();
  });
})();
