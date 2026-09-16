/**
 * dsh-calibre-ebook-translator — 书籍翻译 agent preset plugin.
 *
 * Host half only: on startup it syncs the bundled `book-translator/` preset
 * into the harness-home agent-presets root (`~/.dsh/.agent-presets`), making
 * 「书籍翻译模式」 selectable for new sessions without copying files by hand,
 * and announces the capability through a system-prompt section. No browser
 * half, no routes, no agent tools — the preset itself provides the tools.
 *
 * Structure mirrors dsh-liangshen (Apache-2.0). Zero runtime dependencies.
 */
import { cpSync, existsSync, mkdirSync, rmSync } from 'node:fs'
import { homedir } from 'node:os'
import { isAbsolute, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

/** Stable cordis plugin name; must match the row id in cordis.patch.yml. */
export const name = 'book-translator'

/** Prompt assembly must exist before the announcement section can register. */
export const inject = ['systemPrompt']

/** Absolute path of the bundled preset tree inside this package. */
export function bundledPresetDir() {
  return fileURLToPath(new URL('./book-translator/', import.meta.url))
}

/**
 * Harness home: `DSH_HOME` env override (with `~` expansion; a relative path
 * resolves against the process CWD), platform-home fallback otherwise.
 * Same contract as dsh-liangshen.
 */
export function dshHome() {
  const override = process.env.DSH_HOME
  if (override) {
    let root = override
    if (root === '~') root = homedir()
    else if (root.startsWith('~/') || root.startsWith('~\\')) root = join(homedir(), root.slice(2))
    if (!isAbsolute(root)) root = resolve(process.cwd(), root)
    return root
  }
  return join(homedir(), '.dsh')
}

/** Order of the announcement section within the tool-guidance band. */
const SECTION_ORDER = 150

/** Model-facing announcement: preset presence, scope, and upgrade behavior. */
const ANNOUNCEMENT =
  '本机已安装 dsh-calibre-ebook-translator 插件（书籍翻译模式 agent preset）：新建会话的预设选择器中可选「书籍翻译模式」。该预设面向整书分块翻译：原文由 Calibre 的 ebook-translator 切块逐段输入，术语表、记忆胶囊与进度文件持久保存在工作目录 books/<slug>/ 下，审校由独立子代理完成。preset 文件由插件维护于 ~/.dsh/.agent-presets，插件升级重启后自动更新。用户提到「书籍翻译模式 / book-translator / 开新书」时即指本预设，请据此协作。'

/**
 * Mount the plugin: sync the bundled preset into the harness-home
 * agent-presets root, then announce through a system-prompt section.
 * @param {import('@deepseek-ai/cordis').Context} ctx - host plugin context.
 * @param {{ enabled?: boolean, announceToAgent?: boolean }} [config] - plugin
 *   config row (optional; defaults to enabled + announcing).
 */
export function apply(ctx, config) {
  const cfg = config ?? {}
  const enabled = cfg.enabled !== false
  const announceToAgent = cfg.announceToAgent !== false

  const sync = () => {
    const source = bundledPresetDir()
    if (!existsSync(source)) {
      ctx.logger?.warn?.(`book-translator: bundled preset folder missing: ${source}`)
      return
    }
    const targetRoot = join(dshHome(), '.agent-presets')
    const target = join(targetRoot, 'book-translator')
    try {
      mkdirSync(targetRoot, { recursive: true })
      rmSync(target, { recursive: true, force: true })
      cpSync(source, target, { recursive: true })
      ctx.logger?.info?.(`book-translator: preset synced into ${target}`)
    } catch (error) {
      ctx.logger?.warn?.(`book-translator: preset sync failed: ${error?.message ?? String(error)}`)
    }
  }

  let disposeSection
  const refresh = () => {
    disposeSection?.()
    disposeSection = undefined
    if (!enabled) return
    sync()
    if (!announceToAgent) return
    try {
      disposeSection = ctx.systemPrompt.section({
        name: 'plugin:book-translator',
        order: SECTION_ORDER,
        text: ANNOUNCEMENT,
      })
    } catch (error) {
      ctx.logger?.warn?.(`book-translator: announcement skipped: ${error?.message ?? String(error)}`)
    }
  }

  refresh()
  ctx.effect(() => () => {
    disposeSection?.()
    disposeSection = undefined
  }, 'book-translator: announcement')
}
