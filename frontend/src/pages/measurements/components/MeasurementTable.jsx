import DataTable from '../../../components/common/DataTable.jsx'
import Tag from '../../../components/common/Tag.jsx'
import { DATA_SOURCE_TONE } from '../../../constants/index.js'
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
        <span className={row.compliance_state === 'exceeded' ? 'danger-text strong' : ''}>
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
      key: 'compliance_state',
      title: '达标状态',
      render: (row) => {
        if (row.compliance_state === 'exceeded') return <Tag tone="danger">{formatRatio(row.exceed_ratio)}</Tag>
        if (row.compliance_state === 'qualified') return <Tag tone="success">达标</Tag>
        return <Tag tone="neutral">{row.compliance_label}</Tag>
      }
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
