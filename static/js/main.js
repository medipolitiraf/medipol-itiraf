// Reaksiyon sistemi
async function reaksiyon(emoji, itirafId) {
    try {
        const response = await fetch('/reaksiyon', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ emoji: emoji, itiraf_id: itirafId })
        });
        const data = await response.json();

        // Emoji'den variation selector'ı kaldır (ID için)
        const cleanEmoji = emoji.replace(/️/g, '');
        const sayiEl = document.getElementById('sayi-' + cleanEmoji);
        if (sayiEl) {
            sayiEl.textContent = data.sayi;
        }

        // Butonu aktif/pasif yap
        const btn = document.querySelector(`.reaksiyon-btn[data-emoji="${emoji}"]`);
        if (btn) {
            if (data.status === 'added') {
                btn.classList.add('aktif');
            } else {
                btn.classList.remove('aktif');
            }
        }
    } catch (e) {
        console.error('Reaksiyon hatası:', e);
    }
}

// Karakter sayacı (textarea)
document.querySelectorAll('textarea[maxlength]').forEach(function(ta) {
    const max = ta.getAttribute('maxlength');
    const counter = document.createElement('div');
    counter.style.cssText = 'text-align:right; font-size:11px; color:#aaa; margin-top:-6px; margin-bottom:6px;';
    counter.textContent = '0 / ' + max;
    ta.parentNode.insertBefore(counter, ta.nextSibling);
    ta.addEventListener('input', function() {
        counter.textContent = ta.value.length + ' / ' + max;
    });
});
