import { reactive, ref } from 'vue'

/** 列表页通用逻辑：DRF 分页 {count, results}、筛选条件、加载状态 */
export function useTable(fetcher, initialFilters = {}, { pageSize = 20, ordering = '' } = {}) {
  const filters = reactive({ ...initialFilters })
  const rows = ref([])
  const total = ref(0)
  const loading = ref(false)
  const page = ref(1)
  const size = ref(pageSize)
  const order = ref(ordering)

  async function load(silent = false) {
    if (!silent) loading.value = true
    try {
      const data = await fetcher({ ...filters, page: page.value, page_size: size.value, ordering: order.value })
      rows.value = data.results
      total.value = data.count
    } finally {
      loading.value = false
    }
  }
  function search() { page.value = 1; return load() }
  function reset() {
    for (const k of Object.keys(filters)) filters[k] = initialFilters[k] ?? ''
    return search()
  }
  function onSort({ prop, order: o }) {
    order.value = o ? `${o === 'descending' ? '-' : ''}${prop}` : ordering
    return load()
  }
  return { filters, rows, total, loading, page, size, order, load, search, reset, onSort }
}
