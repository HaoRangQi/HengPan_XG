/**
 * 水波纹：按下时从指针位置扩散，松开后淡出（M3 ripple）。
 *
 * 用事件委托挂在 document 上，凡是 .btn / .icon-btn / .fab / .chip / .tab / 分段按钮 /
 * 带 data-ripple 的元素都自动生效，页面模板不用逐个加指令。
 * 想给某个元素单独加，也可以用 v-ripple 指令。
 */
const SELECTOR = '.btn, .icon-btn, .fab, .chip, .tab, .segmented > *, .nav-item, [data-ripple]';
const reduceMotion = typeof window !== 'undefined' && window.matchMedia
  ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;

function spawn (target, event) {
  if (reduceMotion?.matches) return;
  if (target.disabled || target.getAttribute('aria-disabled') === 'true') return;
  const rect = target.getBoundingClientRect();
  const size = Math.max(rect.width, rect.height) * 2.2;
  const x = (event.clientX ?? rect.left + rect.width / 2) - rect.left - size / 2;
  const y = (event.clientY ?? rect.top + rect.height / 2) - rect.top - size / 2;
  const ripple = document.createElement('span');
  ripple.className = 'md-ripple';
  ripple.style.cssText = `width:${size}px;height:${size}px;left:${x}px;top:${y}px;`;
  // 目标需要能裁剪水波纹
  const style = getComputedStyle(target);
  if (style.position === 'static') target.style.position = 'relative';
  if (style.overflow !== 'hidden') target.style.overflow = 'hidden';
  target.appendChild(ripple);
  const release = () => {
    ripple.classList.add('is-releasing');
    setTimeout(() => ripple.remove(), 600);
    window.removeEventListener('pointerup', release);
    window.removeEventListener('pointercancel', release);
  };
  window.addEventListener('pointerup', release);
  window.addEventListener('pointercancel', release);
}

export function installRipple () {
  document.addEventListener('pointerdown', (event) => {
    if (event.button !== 0) return;
    const target = event.target.closest?.(SELECTOR);
    if (target && !target.hasAttribute('data-no-ripple')) spawn(target, event);
  }, { passive: true });
}

export const vRipple = {
  mounted (el) { el.setAttribute('data-ripple', ''); },
};
