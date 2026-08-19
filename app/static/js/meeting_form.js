(() => {
  const form = document.querySelector("#meeting-form");
  if (!form) return;

  const field = (name) => form.elements.namedItem(name);
  const text = (id, value, fallback) => {
    document.querySelector(id).textContent = value.trim() || fallback;
  };
  const appliedCount = Number(form.dataset.appliedCount || 0);
  const serverError = form.dataset.serverError || "";
  const saveButton = document.querySelector("#meeting-save");
  const errorBox = document.querySelector("#meeting-form-error");
  let dirty = false;

  function updatePreview() {
    const dateValue = document.querySelector("#start-date").value;
    const hourValue = document.querySelector("#start-hour").value;
    const minuteValue = document.querySelector("#start-minute").value;
    field("start_at").value = dateValue ? `${dateValue}T${hourValue}:${minuteValue}` : "";
    text("#preview-place", field("place_name").value, "장소를 입력해주세요");
    text("#preview-neighborhood", field("neighborhood").value, "동네");
    text("#preview-menu", field("representative_menu").value, "대표 메뉴");
    const message = field("host_message").value.trim() || "한마디를 입력해주세요";
    document.querySelector("#preview-message").textContent = `“${message}”`;

    const startValue = field("start_at").value;
    const dateElement = document.querySelector("#preview-datetime");
    if (startValue) {
      const start = new Date(startValue);
      const weekdays = ["일", "월", "화", "수", "목", "금", "토"];
      const pad = (value) => String(value).padStart(2, "0");
      const period = start.getHours() < 12 ? "오전" : "오후";
      const displayHour = start.getHours() % 12 || 12;
      dateElement.textContent = `${start.getFullYear()}.${pad(start.getMonth() + 1)}.${pad(start.getDate())} (${weekdays[start.getDay()]}) ${period} ${displayHour}:${pad(start.getMinutes())}`;
    } else {
      dateElement.textContent = "일시를 입력해주세요";
    }

    const capacity = Math.max(Number(field("capacity").value || 0), 0);
    document.querySelector("#preview-capacity").textContent = capacity;
    document.querySelector("#preview-remaining").textContent = Math.max(capacity - appliedCount, 0);

    const mapLink = document.querySelector("#preview-map");
    const mapUrl = field("place_url").value.trim();
    mapLink.hidden = !mapUrl;
    mapLink.href = mapUrl || "#";
  }

  function updateValidation() {
    const capacity = Number(field("capacity").value || 0);
    let message = "";
    if (capacity < appliedCount) {
      message = `정원은 현재 신청 ${appliedCount}명보다 작게 설정할 수 없습니다.`;
    } else if (!form.checkValidity()) {
      message = "필수 입력값과 입력 형식을 확인해주세요.";
    } else if (!dirty && serverError) {
      message = serverError;
    }
    saveButton.disabled = Boolean(message && message !== serverError) || !form.checkValidity();
    errorBox.textContent = message;
  }

  function update() {
    updatePreview();
    updateValidation();
  }

  form.addEventListener("input", () => { dirty = true; update(); });
  form.addEventListener("change", () => { dirty = true; update(); });
  update();
})();
