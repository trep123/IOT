import { ElMessage } from 'element-plus'

/** 复制文本：非 HTTPS（如按 IP 访问）时 navigator.clipboard 不可用，退回 execCommand。 */
export async function copyText(text, tip = '已复制') {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
    } else {
      const ta = document.createElement('textarea')
      ta.value = text
      ta.style.cssText = 'position:fixed;left:-9999px;top:0'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      ta.remove()
    }
    ElMessage.success(tip)
  } catch {
    ElMessage.error('复制失败，请手动选择复制')
  }
}
