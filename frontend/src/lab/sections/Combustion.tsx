import { useMemo, useState } from 'react';
import { ChartCard } from '../components/ChartCard';
import { StrataTable } from '../components/StrataTable';
import { distributionFigure, scatterFigure } from '../charts/specs';
import type { ViewId } from '../data/selectors';
import { strataFor, viewData, VIEWS } from '../data/selectors';
import { useLab } from '../state/LabContext';
import { useNarrow } from '../state/useNarrow';

const COMBUSTION_VIEWS: ViewId[] = ['k_o2', 'k_pressure', 'k_co2', 'k_he', 'k_d0', 'k_dist'];
const SHORT: Record<string, string> = { k_o2: 'K vs O₂', k_pressure: 'K vs pressure', k_co2: 'K vs CO₂', k_he: 'K vs He', k_d0: 'K vs D₀', k_dist: 'K distributions' };

export function Combustion() {
  const { dataset, filters, chartTheme, selectedKey } = useLab();
  const [viewId, setViewId] = useState<ViewId>('k_o2');
  const [distMode, setDistMode] = useState<'box' | 'ecdf'>('box');
  const narrow = useNarrow();
  const view = VIEWS[viewId];
  const vd = useMemo(() => viewData(dataset.records, view, filters), [dataset, view, filters]);
  const figure = useMemo(
    () => (viewId === 'k_dist' ? distributionFigure(dataset, vd, chartTheme, distMode, selectedKey) : scatterFigure(dataset, vd, chartTheme, selectedKey, narrow)),
    [dataset, vd, chartTheme, distMode, selectedKey, viewId, narrow],
  );
  const strata = view.analysis ? strataFor(dataset, view.analysis, filters.supportModes, filters.fuels) : [];

  return (
    <div className="stack">
      <div className="segmented" role="radiogroup" aria-label="Combustion view">
        {COMBUSTION_VIEWS.map((id) => (
          <button key={id} type="button" role="radio" aria-checked={id === viewId} className={id === viewId ? 'on' : ''} onClick={() => setViewId(id)}>{SHORT[id]}</button>
        ))}
      </div>
      {viewId === 'k_dist' && (
        <div className="segmented small" role="radiogroup" aria-label="Distribution display">
          {(['box', 'ecdf'] as const).map((m) => (
            <button key={m} type="button" role="radio" aria-checked={m === distMode} className={m === distMode ? 'on' : ''} onClick={() => setDistMode(m)}>
              {m === 'box' ? 'Box with every observation' : 'ECDF'}
            </button>
          ))}
        </div>
      )}
      <ChartCard vd={vd} figure={figure}>
        {view.analysis && <StrataTable strata={strata} caption={`v${dataset.analysis_version} ${view.analysis} strata for the selected fuels and support modes`} />}
      </ChartCard>
    </div>
  );
}
