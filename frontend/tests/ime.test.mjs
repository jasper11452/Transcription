import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const source = readFileSync(new URL('../src/lib/ime.ts', import.meta.url), 'utf8')
const js = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020,
  },
}).outputText
const context = { exports: {}, module: { exports: {} } }
context.module.exports = context.exports
vm.runInNewContext(js, context)
const { isImeComposing } = context.module.exports

test('IME composition is detected from isComposing', () => {
  assert.equal(isImeComposing({ isComposing: true, keyCode: 13 }), true)
  assert.equal(isImeComposing({ isComposing: false, keyCode: 13 }), false)
})

test('Safari confirming Enter is caught by keyCode 229', () => {
  assert.equal(isImeComposing({ isComposing: false, keyCode: 229 }), true)
})

test('every custom Enter handler in the task page uses the shared IME guard', () => {
  const taskSource = readFileSync(new URL('../src/task.tsx', import.meta.url), 'utf8')
  assert.ok((taskSource.match(/isImeComposing\(event\.nativeEvent\)/g) ?? []).length >= 3)
})
