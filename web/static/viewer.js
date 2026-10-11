document.querySelectorAll('[data-seek]').forEach(button => {
  button.addEventListener('click', () => {
    const video = document.querySelector('video');
    if (!video) return;
    video.currentTime = Number(button.dataset.seek);
    video.scrollIntoView({behavior: 'smooth', block: 'center'});
  });
});
