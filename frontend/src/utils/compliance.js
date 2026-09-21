import { formatPercent } from './format.js'

/**
 * 达标率统一口径的前端镜像, 判定逻辑必须与后端 domain/compliance.py 保持一致:
 * - 超标单标注为 ignored(已忽略) => 原始数据"已标记无效", 不参与率计算
 * - 无限值(limit_value === null) => "仅记录", 不算达标也不算超标
 * - 其余按 is_exceeded 分为超标 / 达标
 */
export function judgementOf(row) {
  if (row.exceedance_status === 'ignored') {
    return { code: 'invalid', label: '无效', tone: 'neutral' }
  }
  if (row.limit_value === null || row.limit_value === undefined) {
    return { code: 'record_only', label: '仅记录', tone: 'neutral' }
  }
  return row.is_exceeded
    ? { code: 'exceeded', label: '超标', tone: 'danger' }
    : { code: 'compliant', label: '达标', tone: 'success' }
}

/** 统一的达标率脚注: 说明分母构成与无效/无限值剔除, 四处页面共用同一段文案。 */
export function rateFootnote(summary) {
  if (!summary) return ''
  const rate = formatPercent(summary.compliance_rate)
  return `达标率 ${rate} · 参评 ${summary.rateable_count ?? 0} 条(超标 ${summary.exceeded_count ?? 0}) · 无效剔除 ${summary.invalid_count ?? 0} · 无限值不参评 ${summary.unrateable_count ?? 0}`
}
