import DataTable from '../../../components/common/DataTable.jsx'
import Tag from '../../../components/common/Tag.jsx'
import { STATION_STATUS_TONE } from '../../../constants/index.js'
import { formatDate, formatNumber, formatPercent } from '../../../utils/format.js'

export default function StationTable({ rows, loading, onDetail, onEdit, onDelete }) {
  const columns = [
    { key: 'code', title: '监测点编码', className: 'mono cell-nowrap' },
    {
      key: 'name',
      title: '监测点名称',
      render: (row) => (
        <div>
          <div className="strong">{row.name}</div>
          <div className="small muted">{row.address || '未填写详细地址'}</div>
        </div>
      )
    },
    { key: 'area', title: '所属区域', className: 'cell-nowrap' },
    { key: 'station_type_label', title: '类型', className: 'cell-nowrap' },
    {
      key: 'status',
      title: '状态',
      render: (row) => <Tag tone={STATION_STATUS_TONE[row.status]}>{row.status_label}</Tag>
    },
    {
      key: 'installed_at',
      title: '投运日期',
      className: 'cell-nowrap',
      render: (row) => formatDate(row.installed_at)
    },
    {
      key: 'stats',
      title: '数据量',
      align: 'right',
      render: (row) => formatNumber(row.stats?.measurement_count ?? 0, 0)
    },
    {
      key: 'compliance',
      title: '达标率',
      align: 'right',
      render: (row) => (
        <div>
          <div className="strong">{formatPercent(row.stats?.compliance_rate)}</div>
          <div className="small muted">
            参评 {row.stats?.rateable_count ?? 0} · 超标 {row.stats?.exceeded_count ?? 0}
            {(row.stats?.invalid_count ?? 0) > 0 ? ` · 无效 ${row.stats.invalid_count}` : ''}
          </div>
        </div>
      )
    },
    {
      key: 'pending',
      title: '待标注',
      align: 'right',
      render: (row) =>
        row.stats?.pending_count ? (
          <Tag tone="warning">{row.stats.pending_count} 条</Tag>
        ) : (
          <span className="muted">-</span>
        )
    },
    {
      key: 'actions',
      title: '操作',
      align: 'right',
      render: (row) => (
        <div className="btn-group">
          <button type="button" className="btn btn-sm" onClick={() => onDetail(row)}>
            详情
          </button>
          <button type="button" className="btn btn-sm" onClick={() => onEdit(row)}>
            编辑
          </button>
          <button type="button" className="btn btn-sm btn-danger" onClick={() => onDelete(row)}>
            删除
          </button>
        </div>
      )
    }
  ]

  return (
    <DataTable
      columns={columns}
      rows={rows}
      loading={loading}
      emptyText="没有匹配的监测点, 可调整筛选条件或新增监测点"
      emptyIcon="📍"
    />
  )
}
