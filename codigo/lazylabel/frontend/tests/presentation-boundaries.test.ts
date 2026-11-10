// @vitest-environment node
import { readFileSync, readdirSync } from 'node:fs'
import path from 'node:path'
import ts from 'typescript'
import { describe, expect, it } from 'vitest'

function violations(source: string, filename = 'page.tsx') {
  const file = ts.createSourceFile(filename, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
  const found: string[] = []
  function inspect(node: ts.Node) {
    if ((ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) && node.moduleSpecifier && ts.isStringLiteral(node.moduleSpecifier)) {
      const specifier = node.moduleSpecifier.text
      if (/(?:^|\/)lib\/api(?:\.|$)/.test(specifier) || /(?:^|\/)adapters\//.test(specifier)) found.push(`concrete dependency: ${specifier}`)
    }
    // Reject references, too: aliasing fetch must not bypass the network boundary.
    if (ts.isIdentifier(node) && node.text === 'fetch') found.push('network: fetch')
    if (ts.isElementAccessExpression(node) && ts.isStringLiteral(node.argumentExpression) && node.argumentExpression.text === 'fetch') found.push('network: fetch')
    if (ts.isCallExpression(node) && (node.expression.kind === ts.SyntaxKind.ImportKeyword || (ts.isIdentifier(node.expression) && node.expression.text === 'require'))) found.push('dynamic dependency')
    ts.forEachChild(node, inspect)
  }
  inspect(file)
  return found
}

function presentationFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const filename = path.join(directory, entry.name)
    return entry.isDirectory() ? presentationFiles(filename) : /\.tsx?$/.test(entry.name) && !/\.test\./.test(entry.name) ? [filename] : []
  })
}

describe('presentation dependency boundary', () => {
  it.each([
    "fetch('/api')", "window.fetch('/api')", "const request = globalThis['fetch']",
    "import { getSources } from '@/lib/api'", "import type { Health } from '../lib/api'",
    "import { LazyLabelHttpClient } from '@/adapters/http/LazyLabelHttpClient'",
    "export * from '../../adapters/http/LazyLabelHttpClient'", "import('@/lib/api')",
  ])('detects forbidden transport coupling: %s', (source) => {
    expect(violations(source)).not.toEqual([])
  })

  it('allows client-port types and ordinary presentation text', () => {
    expect(violations("import type { Health } from '@/application/ports/LazyLabelClient'; const text = 'fetch data'" )).toEqual([])
  })

  it('keeps all pages and components independent of concrete clients and network requests', () => {
    const root = path.resolve(import.meta.dirname, '../src')
    const failures = ['pages', 'components'].flatMap((directory) => presentationFiles(path.join(root, directory)))
      .flatMap((filename) => violations(readFileSync(filename, 'utf8'), filename).map((reason) => `${path.relative(root, filename)}: ${reason}`))
    expect(failures).toEqual([])
  })
})
