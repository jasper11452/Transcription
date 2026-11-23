import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

// 两个入口各自是一页（没有前端路由），外壳因此是复制出来的；
// 这组断言把「复制出来的部分必须一致」钉住，而不是钉住某一页的排版细节。

const ENTRIES = ['index', 'task']

const html = (name) => readFileSync(new URL(`../${name}.html`, import.meta.url), 'utf8')

const asideOf = (page) => page.slice(page.indexOf('<aside'), page.indexOf('</aside>'))

test('两个入口共用同一套左侧栏外壳', () => {
  for (const name of ENTRIES) {
    const page = html(name)
    assert.equal((page.match(/<aside\b/g) ?? []).length, 1, `${name}: 只能有一个侧栏`)
    assert.ok(!page.includes('<header'), `${name}: 顶部条已删除`)
    assert.ok(page.indexOf('<aside') < page.indexOf('<main'), `${name}: 栏在主区之前`)
    assert.ok(page.indexOf('</aside>') < page.indexOf('id="root"'), `${name}: 动态岛挂在主区一侧`)
  }
})

test('品牌、主题开关、导航与历史都在栏内', () => {
  for (const name of ENTRIES) {
    const aside = asideOf(html(name))
    assert.ok(aside.includes('TRANSCRIPT'), `${name}: 字标在栏内`)
    assert.ok(aside.includes('id="themeToggle"'), `${name}: 主题开关在栏内`)
    assert.ok(aside.includes('＋ 新建转录'), `${name}: 导航行在栏内`)
    assert.ok(aside.includes('id="taskList"'), `${name}: 历史容器在栏内`)
  }
})

test('窄屏回落成顶部一段，历史限高并自己滚', () => {
  for (const name of ENTRIES) {
    const aside = asideOf(html(name))
    const list = aside.slice(aside.indexOf('id="taskList"'))
    const tag = list.slice(0, list.indexOf('>'))
    assert.ok(tag.includes('overflow-y-auto'), `${name}: 历史自己滚，不顶走主区`)
    assert.match(tag, /max-h-\[45vh\]/, `${name}: 窄屏限高`)
    assert.ok(tag.includes('lg:flex-1') && tag.includes('lg:max-h-none'), `${name}: 宽屏撑满栏内剩余高度`)
  }
})

test('历史容器每页只出现一次，供同一个岛 portal', () => {
  for (const name of ENTRIES) {
    assert.equal((html(name).match(/id="taskList"/g) ?? []).length, 1)
  }
})

test('首页自己标当前页，详情页的当前任务交给岛标记', () => {
  assert.match(html('index'), /<a href="\/" aria-current="page"/)
  assert.ok(!html('task').includes('aria-current="page"'))
})
