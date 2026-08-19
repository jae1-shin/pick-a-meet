(() => {
  const card = document.querySelector(".waiting-card[data-remaining-ms]");
  if (!card) return;

  const countdown = document.querySelector("#waiting-countdown");
  const autoRedirect = card.dataset.autoRedirect === "true";
  let deadline = performance.now() + Number(card.dataset.remainingMs);
  let redirectTimer;

  const formatRemaining = (milliseconds) => {
    const totalMilliseconds = Math.max(Math.ceil(milliseconds), 0);
    const totalSeconds = Math.floor(totalMilliseconds / 1000);
    const days = Math.floor(totalSeconds / 86_400);
    const hours = Math.floor((totalSeconds % 86_400) / 3_600);
    const minutes = Math.floor((totalSeconds % 3_600) / 60);
    const seconds = totalSeconds % 60;
    const millisecondsPart = totalMilliseconds % 1000;
    const clock = [hours, minutes, seconds]
      .map((value) => String(value).padStart(2, "0"))
      .join(":") + `.${String(millisecondsPart).padStart(3, "0")}`;
    return days ? `${days}일 ${clock}` : clock;
  };

  const updateCountdown = () => {
    if (countdown) countdown.textContent = formatRemaining(deadline - performance.now());
  };

  const scheduleRedirect = () => {
    window.clearTimeout(redirectTimer);
    const remaining = deadline - performance.now();
    if (remaining <= 0) {
      window.location.replace("/meetings");
      return;
    }
    redirectTimer = window.setTimeout(scheduleRedirect, Math.min(remaining, 60_000));
  };

  const syncWithServer = async () => {
    try {
      const response = await fetch("/registration-window/status", {
        cache: "no-store",
        credentials: "same-origin",
      });
      if (response.ok) {
        const status = await response.json();
        if (status.open) {
          window.location.replace("/meetings");
          return;
        }
        deadline = performance.now() + Number(status.remaining_ms);
        scheduleRedirect();
      }
    } finally {
      window.setTimeout(syncWithServer, 10_000 + Math.random() * 2_000);
    }
  };

  updateCountdown();
  window.setInterval(updateCountdown, 50);
  if (autoRedirect) {
    scheduleRedirect();
    window.setTimeout(syncWithServer, 10_000 + Math.random() * 2_000);
  }
})();
