(() => {
  const toast = document.querySelector("#app-toast");
  if (!toast) return;
  let timer;

  window.showToast = (message, type = "success") => {
    clearTimeout(timer);
    toast.textContent = message;
    toast.className = `toast show ${type}`;
    timer = setTimeout(() => toast.classList.remove("show"), 3200);
  };

  if (toast.classList.contains("show")) {
    timer = setTimeout(() => toast.classList.remove("show"), 3200);
  }
})();
