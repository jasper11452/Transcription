// 两个 HTML 入口共用：在首屏绘制前恢复主题，不依赖 React 是否挂载成功。
(() => {
  const storageKey = 'transcript-theme'
  const root = document.documentElement
  const system = window.matchMedia('(prefers-color-scheme: light)')
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
  const readPreference = () => {
    try {
      const value = localStorage.getItem(storageKey)
      return value === 'light' || value === 'dark' ? value : null
    } catch {
      return null
    }
  }
  let preference = readPreference()

  const apply = () => {
    const light = (preference ?? (system.matches ? 'light' : 'dark')) === 'light'
    root.classList.toggle('light', light)
    root.classList.toggle('dark', !light)
    root.style.colorScheme = light ? 'light' : 'dark'
    const button = document.getElementById('themeToggle')
    if (button) {
      const target = light ? '深色模式' : '浅色模式'
      button.textContent = target
      button.setAttribute('aria-label', `切换到${target}`)
      button.title = `当前为${light ? '浅色' : '深色'}模式`
    }
  }

  apply()

  const setTheme = (next) => {
    preference = next
    // 存储被禁用时仍可切换，只是不跨刷新保存。
    try { localStorage.setItem(storageKey, preference) } catch {}
    apply()
  }

  // 「划到哪变到哪」：旧主题快照留下层，新主题快照自上而下裁开，
  // 分界线扫过的位置就是主题已经切完的位置。
  const canWipe = typeof document.startViewTransition === 'function'
  let running = false
  let releaseTimer

  const release = () => {
    running = false
    if (releaseTimer !== undefined) {
      clearTimeout(releaseTimer)
      releaseTimer = undefined
    }
    delete root.dataset.themeTransition
  }

  const wipeTheme = (next) => {
    // 频繁点击时不叠加过渡；等本次结束后再接受下一次。
    if (running) return
    if (!canWipe || reducedMotion.matches) {
      setTheme(next)
      return
    }
    running = true
    root.dataset.themeTransition = '1'
    // 兜底：过渡被打断或事件丢失时，锁必须在有限时间内释放，不能卡死主题开关。
    releaseTimer = setTimeout(release, 1500)
    let transition
    try {
      transition = document.startViewTransition(() => setTheme(next))
    } catch {
      setTheme(next)
      release()
      return
    }
    transition.finished.finally(release)
  }

  document.addEventListener('DOMContentLoaded', () => {
    apply()
    document.getElementById('themeToggle')?.addEventListener('click', () => {
      wipeTheme(root.classList.contains('light') ? 'dark' : 'light')
    })
  }, { once: true })
  system.addEventListener('change', () => { if (!preference) apply() })
  window.addEventListener('storage', (event) => {
    if (event.key === storageKey || event.key === null) {
      preference = readPreference()
      apply()
    }
  })
})()