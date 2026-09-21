import { useEffect, useState } from 'react'
import { FilterPanel } from '../../../components/common/Card.jsx'
import { Field, Input, Select } from '../../../components/common/FormField.jsx'
import { usePollutantMeta, useStationOptions } from '../../../hooks/useOptions.js'

const PERIODS = [
  { value: 'hourly', label: '小时均值' },
  { value: 'daily', label: '日均值' }
]

const EXCEEDED_OPTIONS = [
  { value: 'true', label: '自动判定超标' },
  { value: 'false', label: '自动判定未超标' }
]

export default function MeasurementFilters({ value, loading, onSubmit, onReset }) {
  const [draft, setDraft] = useState(value)
  const { data: stationData } = useStationOptions()
  const { data: pollutantData } = usePollutantMeta()

  useEffect(() => {
    setDraft(value)
  }, [value])

  const update = (key) => (event) => setDraft({ ...draft, [key]: event.target.value })

  return (
    <FilterPanel
      loading={loading}
      onSearch={() => onSubmit(draft)}
      onReset={() => {
        setDraft({ station_id: '', pollutant: '', period: '', is_exceeded: '', date_from: '', date_to: '' })
        onReset()
      }}
    >
      <Field label="监测点">
        <Select
          value={draft.station_id || ''}
          onChange={update('station_id')}
          placeholder="全部监测点"
          options={(stationData?.items ?? []).map((item) => ({
            value: String(item.id),
            label: `${item.code} ${item.name}`
          }))}
        />
      </Field>
      <Field label="监测因子">
        <Select
          value={draft.pollutant || ''}
          onChange={update('pollutant')}
          placeholder="全部因子"
          options={(pollutantData?.items ?? []).map((item) => ({ value: item.code, label: item.label }))}
        />
      </Field>
      <Field label="数据周期">
        <Select value={draft.period || ''} onChange={update('period')} placeholder="全部周期" options={PERIODS} />
      </Field>
      <Field label="自动超标判定">
        <Select value={draft.is_exceeded || ''} onChange={update('is_exceeded')} placeholder="全部" options={EXCEEDED_OPTIONS} />
      </Field>
      <Field label="开始日期">
        <Input type="date" value={draft.date_from || ''} onChange={update('date_from')} />
      </Field>
      <Field label="结束日期">
        <Input type="date" value={draft.date_to || ''} onChange={update('date_to')} />
      </Field>
    </FilterPanel>
  )
}
