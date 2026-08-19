(() => {
  const applyEnabled = document.querySelector("#member-apply-enabled");
  const hostEnabled = document.querySelector("#member-host-enabled");
  if (!applyEnabled || !hostEnabled) return;

  const syncPermissions = () => {
    if (hostEnabled.checked) applyEnabled.checked = false;
    applyEnabled.disabled = hostEnabled.checked;
  };

  hostEnabled.addEventListener("change", syncPermissions);
  syncPermissions();
})();
