(() => {
  const button = document.querySelector("#copy-applicants");
  const source = document.querySelector("#applicant-copy-source");
  if (!button || !source) return;

  button.addEventListener("click", async () => {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(source.value);
      } else {
        source.hidden = false;
        source.select();
        document.execCommand("copy");
        source.hidden = true;
      }
      window.showToast("신청자 명단을 클립보드에 복사했습니다.");
    } catch (_) {
      window.showToast(
        "복사하지 못했습니다. 브라우저의 클립보드 권한을 확인해주세요.",
        "danger",
      );
    }
  });
})();
