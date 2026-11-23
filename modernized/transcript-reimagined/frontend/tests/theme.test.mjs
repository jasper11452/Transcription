import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import vm from 'node:vm'

const script = readFileSync(new URL('../public/theme.js', import.meta.url), 'utf8')

function browser({ stored = null, systemLight = false, blocked = false, startViewTransition = null } = {}) {
  let value = stored
  const classes = new Set()
  const documentEvents = {}
  const windowEvents = {}
  const attributes = {}
  const buttonEvents = {}
  const timers = []
  const button = {
    textContent: '',
    setAttribute: (key, v) => { attributes[key] = v },
    addEventListener: (key, callback) => { buttonEvents[key] = callback },
  }
  const system = {
    matches: systemLight,
    addEventListener: (_, callback) => { system.change = callback },
  }
  const root = {
    dataset: {},
    style: {},
    classList: {
      toggle: (name, enabled) => enabled ? classes.add(name) : classes.delete(name),
      contains: (name) => classes.has(name),
    },
  }
  const context = {
    document: {
      documentElement: root,
      getElementById: () => button,
      addEventListener: (key, callback) => { documentEvents[key] = callback },
      ...(startViewTransition ? { startViewTransition } : {}),
    },
    window: {
      matchMedia: () => system,
      addEventListener: (key, callback) => { windowEvents[key] = callback },
    },
    setTimeout: (fn) => { timers.push(fn); return timers.length },
    clearTimeout: () => {},
    localStorage: {
      getItem: () => { if (blocked) throw new Error('blocked'); return value },
      setItem: (_, next) => { if (blocked) throw new Error('blocked'); value = next },
    },
  }
  vm.runInNewContext(script, context)
  return {
    classes, root, button, attributes, system,
    ready: () => documentEvents.DOMContentLoaded(),
    click: () => buttonEvents.click(),
    stored: () => value,
    runs: () => timers.map((fn) => fn()),
    storage: (next) => { value = next; windowEvents.storage({ key: 'transcript-theme' }) },
  }
}

test('both HTML entries load the same blocking theme script before the app', () => {
  for (const name of ['index', 'task']) {
    const html = readFileSync(new URL(`../${name}.html`, import.meta.url), 'utf8')
    assert.match(html, /<script src="\/theme.js"><\/script>/)
    assert.ok(html.indexOf('/theme.js') < html.indexOf('type="module"'))
    assert.equal((html.match(/id="themeToggle"/g) ?? []).length, 1)
  }
})

test('saved light applies before DOM ready, persists and has accurate action labels', () => {
  const b = browser({ stored: 'light' })
  assert.ok(b.classes.has('light'))
  assert.equal(b.root.style.colorScheme, 'light')
  b.ready()
  assert.equal(b.attributes['aria-label'], '切换到深色模式')
  b.click()
  assert.equal(b.stored(), 'dark')
  assert.ok(b.classes.has('dark'))
  assert.equal(b.button.textContent, '浅色模式')
  b.click()
  assert.equal(b.stored(), 'light')
})

test('follows system until explicit selection and synchronizes other tabs', () => {
  const b = browser({ systemLight: true })
  b.ready()
  assert.equal(b.stored(), null)
  b.system.matches = false
  b.system.change()
  assert.ok(b.classes.has('dark'))
  b.click()
  b.system.change()
  assert.ok(b.classes.has('light'))
  b.storage('dark')
  assert.ok(b.classes.has('dark'))
  b.storage(null)
  b.system.matches = true
  b.system.change()
  assert.ok(b.classes.has('light'))
})

test('storage failure does not disable the theme button', () => {
  const b = browser({ blocked: true })
  b.ready()
  b.click()
  assert.ok(b.classes.has('light'))
  b.click()
  assert.ok(b.classes.has('dark'))
})

test('theme swap is handed to the view transition and a second click waits its turn', async () => {
  let finish
  const swaps = []
  const b = browser({
    startViewTransition: (callback) => {
      swaps.push(callback)
      callback()
      return { finished: new Promise((resolve) => { finish = resolve }) }
    },
  })
  b.ready()

  b.click()
  assert.equal(swaps.length, 1)
  assert.ok(b.classes.has('light'))

  // 过渡进行中：不叠加第二次换色，也不动已存偏好。
  b.click()
  assert.equal(swaps.length, 1)
  assert.equal(b.stored(), 'light')

  finish()
  await Promise.resolve()
  b.click()
  assert.equal(swaps.length, 2)
  assert.ok(b.classes.has('dark'))
})

test('a transition that never finishes still releases the theme button', () => {
  const b = browser({
    // 永不 settle 的 finished：只能靠超时兜底解锁。
    startViewTransition: (callback) => { callback(); return { finished: new Promise(() => {}) } },
  })
  b.ready()
  b.click()
  assert.equal(b.root.dataset.themeTransition, '1')
  b.click()
  assert.ok(b.classes.has('light'))
  assert.equal(b.stored(), 'light')
  b.runs()
  assert.equal(b.root.dataset.themeTransition, undefined)
})
