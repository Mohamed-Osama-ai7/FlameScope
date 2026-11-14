import { useEffect, useState } from 'react';

/** True below the mobile breakpoint; charts then stack fuel panels in one column. */
export function useNarrow(maxWidth = 700): boolean {
  const query = `(max-width: ${maxWidth}px)`;
  const [narrow, setNarrow] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const m = window.matchMedia(query);
    const on = () => setNarrow(m.matches);
    m.addEventListener('change', on);
    on();
    return () => m.removeEventListener('change', on);
  }, [query]);
  return narrow;
}
