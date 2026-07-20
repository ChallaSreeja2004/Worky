/**
 * src/context/outlookStateContext.ts
 * ====================================
 * Context definition for OutlookState — the connector refresh callback,
 * connector status, and last-fetched timestamp consumed by WidgetShell.
 *
 * This file is non-component (no JSX, no default export of a component) so
 * it satisfies the oxlint react/only-export-components rule.  The Provider
 * is rendered inside ScreenManager.tsx.  The consumer hook is here.
 *
 * Pattern mirrors authContextDef.ts / AuthContext.tsx / useAuth.ts.
 */

import { createContext, useContext } from 'react'
import type { ConnectorStatus } from '../types/index.ts'

export interface OutlookStateContextValue {
  refresh: () => void
  connectorStatus: ConnectorStatus | null
  /** ISO 8601 collected_at string from the last successful fetch, or null. */
  collectedAt: string | null
  isRefreshing: boolean
}

export const OutlookStateContext = createContext<OutlookStateContextValue>({
  refresh: () => {},
  connectorStatus: null,
  collectedAt: null,
  isRefreshing: false,
})

export function useOutlookState(): OutlookStateContextValue {
  return useContext(OutlookStateContext)
}
