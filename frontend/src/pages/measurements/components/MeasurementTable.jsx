import DataTable from '../../../components/common/DataTable.jsx'
import Tag from '../../../components/common/Tag.jsx'
import { DATA_SOURCE_TONE, EXCEEDANCE_STATUS_TONE } from '../../../constants/index.js'
import { judgementOf } from '../../../utils/compliance.js'
import { formatDateTime, formatNumber, formatRatio } from '../../../utils/format.js'

export default function MeasurementTable({ rows, loading, onDelete }) {
  const columns = [
    { key: 'measured_at', title: '监测时间', className: 'cell-nowrap', render: (row) => formatDateTime(row.measured_at) },
    {
      key: 'station',
      title: '监测点',
      render: (row) => (
        <div>
          <div>{row.station?.name || '-'}</div>
          <div className="small muted mono">{row.station?.code || ''}</div>
        </div>
      )
    },
    { key: 'pollutant_label', title: '监测因子', className: 'cell-nowrap' },
    { key: 'period_label', title: '周期', className: 'cell-nowrap' },
    {
      key: 'value',
      title: '监测值',
      align: 'right',
      className: 'cell-nowrap',
      render: (row) => (
        <span className={row.is_exceeded && row.exceedance_status !== 'ignored' ? 'danger-text strong' : ''}>
          {formatNumber(row.value)} <span className="muted small">{row.unit}</span>
        </span>
      )
    },
    {
      key: 'limit_value',
      title: '限值',
      align: 'right',
      render: (row) => (row.limit_value === null ? <span className="muted small">无限值</span> : formatNumber(row.limit_value))
    },
    {
      key: 'is_exceeded',
      title: '判定',
      render: (row) => {
        const judgement = judgementOf(row)
        if (judgement.code === 'exceeded') return <Tag tone="danger">超标 {formatRatio(row.exceed_ratio)}</Tag>
        return <Tag tone={judgement.tone}>{judgement.label}</Tag>
      }
    },
    {
      key: 'exceedance_status',
      title: '标注状态',
      render: (row) =>
        row.exceedance_status ? (
          <Tag tone={EXCEEDANCE_STATUS_TONE[row.exceedance_status]}>
            {row.exceedance_status === 'pending' ? '待标注' : row.exceedance_status === 'confirmed' ? '已确认' : '已忽略(无效)'}
          </Tag>
        ) : (
          <span className="muted">-</span>
        )
    },
    {
      key: 'data_source_label',
      title: '来源',
      render: (row) => <Tag tone={DATA_SOURCE_TONE[row.data_source]}>{row.data_source_label}</Tag>
    },
    { key: 'recorder', title: '录入人', render: (row) => row.recorder || '-' },
    {
      key: 'actions',
      title: '操作',
      align: 'right',
      render: (row) => (
        <button type="button" className="btn btn-sm btn-danger" onClick={() => onDelete(row)}>
          删除
        </button>
      )
    }
  ]

  return (
    <DataTable
      columns={columns}
      rows={rows}
      loading={loading}
      emptyText="暂无监测数据, 请先在上方录入"
      emptyIcon="✍️"
    />
  )
}
